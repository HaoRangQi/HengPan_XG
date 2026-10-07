"""Versioned boundary for explicit bar-count fields; old Python names remain internal."""
from pydantic import BaseModel, ConfigDict, model_validator

BAR_ALIASES = {'high_point_lookback_bars':'high_point_lookback_days',
               'rapid_decline_bars':'rapid_decline_days',
               'breakthrough_confirmation_bars':'breakthrough_confirmation_days'}

class ScanParameters(BaseModel):
    model_config = ConfigDict(populate_by_name=True)
    params_semantics_version: int = 2

    @model_validator(mode='before')
    @classmethod
    def resolve_units(cls, value):
        if not isinstance(value,dict):return value
        data=dict(value)
        for public, internal in BAR_ALIASES.items():
            if public in data and internal in data and data[public] != data[internal]:
                raise ValueError(f'conflicting values for {public} and legacy {internal}')
        if data.get('params_semantics_version',2) not in (1,2):
            raise ValueError('unsupported parameter semantics version')
        # New requests execute corrected semantics. Old snapshots are never rewritten.
        data['params_semantics_version']=2
        return data
