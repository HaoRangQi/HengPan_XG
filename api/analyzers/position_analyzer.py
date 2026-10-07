"""
Position Analyzer module for analyzing stock price position relative to historical highs.
"""
import pandas as pd
import numpy as np
from typing import Dict, Any, Tuple

def analyze_position(df: pd.DataFrame, 
                    high_point_lookback_days: int = 365,
                    decline_period_days: int = 180,
                    decline_threshold: float = 0.5) -> Dict[str, Any]:
    """
    Analyze if a stock is at a low position relative to its historical high.
    
    Args:
        df: DataFrame containing stock price data
        high_point_lookback_days: Number of K-line bars to look back (legacy parameter name)
        decline_period_days: Maximum elapsed calendar days for the decline
        decline_threshold: Minimum decline percentage from high to be considered at low position (0.5 = 50%)
    
    Returns:
        Dict containing position analysis results
    """
    if df.empty or len(df) < max(30, high_point_lookback_days):  # Require at least 30 days of data
        return {
            "is_low_position": False,
            "details": {"status": "数据不足"}
        }
    
    # Sort by date to ensure chronological order
    df = df.sort_values('date').reset_index(drop=True)
    
    # Get current price (most recent close)
    current_price = df['close'].iloc[-1]
    
    # Limit the lookback period for finding the high point
    lookback_df = df.iloc[-min(len(df), high_point_lookback_days):]
    
    # Find the historical high in the lookback period
    historical_high = lookback_df['high'].max()
    high_date_series = lookback_df.loc[lookback_df['high'] == historical_high, 'date']
    
    # Handle case where multiple dates have the same high
    if len(high_date_series) > 0:
        high_date = high_date_series.iloc[0]
    else:
        # Fallback if no exact match (shouldn't happen but just in case)
        high_date = lookback_df.iloc[lookback_df['high'].argmax()]['date']
    
    # Calculate the decline percentage
    decline_pct = (historical_high - current_price) / historical_high
    
    # Check if the high point occurred within the decline period
    days_since_high = (pd.to_datetime(df['date'].iloc[-1]) - pd.to_datetime(high_date)).total_seconds() / 86400

    # Determine if the stock is at a low position
    is_low_position = (decline_pct >= decline_threshold) and (days_since_high <= decline_period_days)
    
    # Prepare details
    details = {
        "current_price": round(float(current_price), 2),
        "historical_high": round(float(historical_high), 2),
        "high_date": high_date,
        "decline_pct": round(float(decline_pct * 100), 2),
        "days_since_high": int(days_since_high),
        "decline_threshold": round(float(decline_threshold * 100), 2),
        "decline_period_days": decline_period_days,
        "status": "低位" if is_low_position else "非低位"
    }
    
    return {
        "is_low_position": is_low_position,
        "details": details
    }
