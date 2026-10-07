"""
API endpoints for case management.
"""
import sqlite3
import pandas as pd
from fastapi import APIRouter, HTTPException, Body, Path
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from .case_manager import (
    get_cases, get_case, get_migration_status, create_case, update_case,
    delete_case, create_anjishi_case, create_case_from_analysis
)
from .json_utils import sanitize_float_for_json
from .case_store import CaseMigrationError

# Create router
router = APIRouter()


def _case_operation(operation, *args, **kwargs):
    try:
        return operation(*args, **kwargs)
    except CaseMigrationError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except (sqlite3.Error, OSError) as exc:
        raise HTTPException(status_code=503, detail=f"案例存储不可用：{exc}") from exc


# Define models


class CaseMetadata(BaseModel):
    id: str = Field(description="案例 ID")
    title: str = Field(description="案例标题")
    stockCode: str = Field(description="证券代码")
    stockName: str = Field(description="证券名称")
    createdAt: str = Field(description="创建时间")
    updatedAt: str = Field(description="更新时间")
    tags: List[str] = Field(description="标签")


class CaseListResponse(BaseModel):
    cases: List[CaseMetadata] = Field(description="案例列表")
    lastUpdated: str = Field(description="最近一次更新时间")
    migration: Dict[str, Any] = Field(description="旧案例迁移结果及缺失可选附件提示")


class CaseCreateRequest(BaseModel):
    title: str
    stockCode: str
    stockName: str
    tags: Optional[List[str]] = None
    description: Optional[str] = None


class CaseUpdateRequest(BaseModel):
    title: Optional[str] = None
    tags: Optional[List[str]] = None
    description: Optional[str] = None


# Define routes
@router.get("/cases", response_model=CaseListResponse, summary="案例列表",
            description="返回全部案例的基本信息，不含分析结果与 K 线数据。")
async def list_cases():
    """
    Get all cases.
    """
    cases = _case_operation(get_cases)
    # Sanitize the cases data to handle NaN values
    sanitized_cases = sanitize_float_for_json(cases)
    return {
        "cases": sanitized_cases,
        "migration": _case_operation(get_migration_status),
        "lastUpdated": max((case["updatedAt"] for case in cases), default="")
    }


@router.get("/cases/{case_id}", summary="案例详情",
            description="返回单个案例的完整数据，包括分析结果与 K 线数据。",
            responses={404: {"description": "案例不存在"}})
async def get_case_by_id(case_id: str = Path(description="案例 ID")):
    """
    Get a specific case by ID.
    """
    case_data = _case_operation(get_case, case_id)
    if not case_data:
        raise HTTPException(status_code=404, detail="案例不存在")

    # Sanitize the case data to handle NaN values
    sanitized_data = sanitize_float_for_json(case_data)
    return sanitized_data


@router.post("/cases", summary="新建案例",
             description="请求体为 JSON，必须包含 title、stockCode、stockName；ID 由服务器生成。",
             responses={400: {"description": "缺少必填字段"}})
async def create_new_case(case_data: Dict[str, Any] = Body(...)):
    """
    Create a new case.
    """
    try:
        result = _case_operation(create_case, case_data)
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"创建案例失败：{str(e)}")


@router.put("/cases/{case_id}", summary="更新案例",
            description="用请求体中的字段覆盖案例的对应字段。",
            responses={404: {"description": "案例不存在"}})
async def update_existing_case(case_id: str = Path(description="案例 ID"), case_data: Dict[str, Any] = Body(...)):
    """
    Update an existing case.
    """
    result = _case_operation(update_case, case_id, case_data)
    if not result:
        raise HTTPException(status_code=404, detail="案例不存在")
    return result


@router.delete("/cases/{case_id}", summary="删除案例",
               description="删除案例及其保存的数据，返回 {\"success\": true}。",
               responses={404: {"description": "案例不存在"}})
async def delete_existing_case(case_id: str = Path(description="案例 ID")):
    """
    Delete a case.
    """
    success = _case_operation(delete_case, case_id)
    if not success:
        raise HTTPException(status_code=404, detail="案例不存在")
    return {"success": True}


@router.post("/cases/create-anjishi", summary="生成安记食品示例案例",
             description="按内置分析结果创建安记食品（sh.603696）案例，用于演示。")
async def create_anjishi_case_endpoint():
    """
    Create a case for Anjishi (安记食品) based on our analysis.
    """
    try:
        result = _case_operation(create_anjishi_case)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"创建安记食品案例失败：{str(e)}")


class ExportCaseRequest(BaseModel):
    """
    Request model for exporting a stock to case library.
    """
    stockData: Dict[str, Any] = Field(description="股票信息：code、name、industry")
    analysisResult: Dict[str, Any] = Field(description="分析结果：入选理由、扫描参数、标记线等")
    klineData: List[Dict[str, Any]] = Field(description="日线数据")


@router.post("/cases/export", summary="扫描结果存为案例",
             description="把扫描结果中的一只股票连同分析结果与 K 线数据存入案例库，返回新案例 ID。")
async def export_to_case(request: ExportCaseRequest = Body(...)):
    """
    Export a stock analysis result to the case library.
    """
    try:
        # Convert klineData to DataFrame
        kline_df = pd.DataFrame(
            request.klineData) if request.klineData else pd.DataFrame()

        # Generate a title if not provided
        if "title" not in request.stockData:
            request.stockData["title"] = f"{request.stockData.get('name', '')}({request.stockData.get('code', '')})平台期分析"

        # Create case from analysis
        result = _case_operation(create_case_from_analysis,
            stock_data=request.stockData,
            analysis_result=request.analysisResult,
            kline_data=kline_df
        )

        return {"success": True, "case_id": result.get("id"), "message": "案例创建成功"}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"存为案例失败：{str(e)}")
