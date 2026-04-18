# MyTT indicators adapted for local parquet-backed Active Portfolio workflows.

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np
import pandas as pd

from activeportfolio.dataflows.config import get_config
from activeportfolio.dataflows.market_data_store import load_history_window


# ------------------ 0-level core helpers ---------------------------------------
def RD(N, D=3):
    return np.round(N, D)


def RET(S, N=1):
    return np.array(S)[-N]


def ABS(S):
    return np.abs(S)


def MAX(S1, S2):
    return np.maximum(S1, S2)


def MIN(S1, S2):
    return np.minimum(S1, S2)


def MA(S, N):
    return pd.Series(S).rolling(N).mean().values


def REF(S, N=1):
    return pd.Series(S).shift(N).values


def DIFF(S, N=1):
    return pd.Series(S).diff(N).values


def STD(S, N):
    return pd.Series(S).rolling(N).std(ddof=0).values


def IF(S_BOOL, S_TRUE, S_FALSE):
    return np.where(S_BOOL, S_TRUE, S_FALSE)


def SUM(S, N):
    return pd.Series(S).rolling(N).sum().values


def HHV(S, N):
    return pd.Series(S).rolling(N).max().values


def LLV(S, N):
    return pd.Series(S).rolling(N).min().values


def EMA(S, N):
    return pd.Series(S).ewm(span=N, adjust=False).mean().values


def SMA(S, N, M=1):
    return pd.Series(S).ewm(alpha=M / N, adjust=False).mean().values


def AVEDEV(S, N):
    avedev = pd.Series(S).rolling(N).apply(lambda x: (np.abs(x - x.mean())).mean())
    return avedev.values


def SLOPE(S, N, RS=False):
    M = pd.Series(S[-N:])
    poly = np.polyfit(M.index, M.values, deg=1)
    Y = np.polyval(poly, M.index)
    if RS:
        return Y[1] - Y[0], Y
    return Y[1] - Y[0]


# ------------------ 1-level application helpers --------------------------------
def COUNT(S_BOOL, N):
    return SUM(S_BOOL, N)


def EVERY(S_BOOL, N):
    R = SUM(S_BOOL, N)
    return IF(R == N, True, False)


def LAST(S_BOOL, A, B):
    if A < B:
        A = B
    return S_BOOL[-A:-B].sum() == (A - B)


def EXIST(S_BOOL, N=5):
    R = SUM(S_BOOL, N)
    return IF(R > 0, True, False)


def BARSLAST(S_BOOL):
    M = np.argwhere(S_BOOL)
    return len(S_BOOL) - int(M[-1]) - 1 if M.size > 0 else -1


def FORCAST(S, N):
    K, Y = SLOPE(S, N, RS=True)
    return Y[-1] + K


def CROSS(S1, S2):
    CROSS_BOOL = IF(S1 > S2, True, False)
    return COUNT(CROSS_BOOL > 0, 2) == 1


# ------------------ 2-level indicators -----------------------------------------
def MACD(CLOSE, SHORT=12, LONG=26, M=9):
    DIF = EMA(CLOSE, SHORT) - EMA(CLOSE, LONG)
    DEA = EMA(DIF, M)
    MACD_VALUE = (DIF - DEA) * 2
    return RD(DIF), RD(DEA), RD(MACD_VALUE)


def KDJ(CLOSE, HIGH, LOW, N=9, M1=3, M2=3):
    RSV = (CLOSE - LLV(LOW, N)) / (HHV(HIGH, N) - LLV(LOW, N)) * 100
    K = EMA(RSV, (M1 * 2 - 1))
    D = EMA(K, (M2 * 2 - 1))
    J = K * 3 - D * 2
    return K, D, J


def RSI(CLOSE, N=24):
    DIF = CLOSE - REF(CLOSE, 1)
    return RD(SMA(MAX(DIF, 0), N) / SMA(ABS(DIF), N) * 100)


def WR(CLOSE, HIGH, LOW, N=10, N1=6):
    WR_VALUE = (HHV(HIGH, N) - CLOSE) / (HHV(HIGH, N) - LLV(LOW, N)) * 100
    WR1 = (HHV(HIGH, N1) - CLOSE) / (HHV(HIGH, N1) - LLV(LOW, N1)) * 100
    return RD(WR_VALUE), RD(WR1)


def BIAS(CLOSE, L1=6, L2=12, L3=24):
    BIAS1 = (CLOSE - MA(CLOSE, L1)) / MA(CLOSE, L1) * 100
    BIAS2 = (CLOSE - MA(CLOSE, L2)) / MA(CLOSE, L2) * 100
    BIAS3 = (CLOSE - MA(CLOSE, L3)) / MA(CLOSE, L3) * 100
    return RD(BIAS1), RD(BIAS2), RD(BIAS3)


def BOLL(CLOSE, N=20, P=2):
    MID = MA(CLOSE, N)
    UPPER = MID + STD(CLOSE, N) * P
    LOWER = MID - STD(CLOSE, N) * P
    return RD(UPPER), RD(MID), RD(LOWER)


def PSY(CLOSE, N=12, M=6):
    PSY_VALUE = COUNT(CLOSE > REF(CLOSE, 1), N) / N * 100
    PSYMA = MA(PSY_VALUE, M)
    return RD(PSY_VALUE), RD(PSYMA)


def CCI(CLOSE, HIGH, LOW, N=14):
    TP = (HIGH + LOW + CLOSE) / 3
    return (TP - MA(TP, N)) / (0.015 * AVEDEV(TP, N))


def ATR(CLOSE, HIGH, LOW, N=20):
    TR = MAX(MAX((HIGH - LOW), ABS(REF(CLOSE, 1) - HIGH)), ABS(REF(CLOSE, 1) - LOW))
    return MA(TR, N)


def BBI(CLOSE, M1=3, M2=6, M3=12, M4=20):
    return (MA(CLOSE, M1) + MA(CLOSE, M2) + MA(CLOSE, M3) + MA(CLOSE, M4)) / 4


def DMI(CLOSE, HIGH, LOW, M1=14, M2=6):
    TR = SUM(MAX(MAX(HIGH - LOW, ABS(HIGH - REF(CLOSE, 1))), ABS(LOW - REF(CLOSE, 1))), M1)
    HD = HIGH - REF(HIGH, 1)
    LD = REF(LOW, 1) - LOW
    DMP = SUM(IF((HD > 0) & (HD > LD), HD, 0), M1)
    DMM = SUM(IF((LD > 0) & (LD > HD), LD, 0), M1)
    PDI = DMP * 100 / TR
    MDI = DMM * 100 / TR
    ADX = MA(ABS(MDI - PDI) / (PDI + MDI) * 100, M2)
    ADXR = (ADX + REF(ADX, M2)) / 2
    return PDI, MDI, ADX, ADXR


def TAQ(HIGH, LOW, N):
    UP = HHV(HIGH, N)
    DOWN = LLV(LOW, N)
    MID = (UP + DOWN) / 2
    return UP, MID, DOWN


def TRIX(CLOSE, M1=12, M2=20):
    TR = EMA(EMA(EMA(CLOSE, M1), M1), M1)
    TRIX_VALUE = (TR - REF(TR, 1)) / REF(TR, 1) * 100
    TRMA = MA(TRIX_VALUE, M2)
    return TRIX_VALUE, TRMA


def VR(CLOSE, VOL, M1=26):
    LC = REF(CLOSE, 1)
    return SUM(IF(CLOSE > LC, VOL, 0), M1) / SUM(IF(CLOSE <= LC, VOL, 0), M1) * 100


def EMV(HIGH, LOW, VOL, N=14, M=9):
    VOLUME = MA(VOL, N) / VOL
    MID = 100 * (HIGH + LOW - REF(HIGH + LOW, 1)) / (HIGH + LOW)
    EMV_VALUE = MA(MID * VOLUME * (HIGH - LOW) / MA(HIGH - LOW, N), N)
    MAEMV = MA(EMV_VALUE, M)
    return EMV_VALUE, MAEMV


def DPO(CLOSE, M1=20, M2=10, M3=6):
    DPO_VALUE = CLOSE - REF(MA(CLOSE, M1), M2)
    MADPO = MA(DPO_VALUE, M3)
    return DPO_VALUE, MADPO


def BRAR(OPEN, CLOSE, HIGH, LOW, M1=26):
    AR = SUM(HIGH - OPEN, M1) / SUM(OPEN - LOW, M1) * 100
    BR = SUM(MAX(0, HIGH - REF(CLOSE, 1)), M1) / SUM(MAX(0, REF(CLOSE, 1) - LOW), M1) * 100
    return AR, BR


def DMA(CLOSE, N1=10, N2=50, M=10):
    DIF = MA(CLOSE, N1) - MA(CLOSE, N2)
    DIFMA = MA(DIF, M)
    return DIF, DIFMA


def MTM(CLOSE, N=12, M=6):
    MTM_VALUE = CLOSE - REF(CLOSE, N)
    MTMMA = MA(MTM_VALUE, M)
    return MTM_VALUE, MTMMA


def ROC(CLOSE, N=12, M=6):
    ROC_VALUE = 100 * (CLOSE - REF(CLOSE, N)) / REF(CLOSE, N)
    MAROC = MA(ROC_VALUE, M)
    return ROC_VALUE, MAROC


@dataclass(frozen=True)
class IndicatorSpec:
    func: Callable[..., object]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    description: str


INDICATOR_SPECS: dict[str, IndicatorSpec] = {
    "macd": IndicatorSpec(MACD, ("Close",), ("DIF", "DEA", "MACD"), "Moving average convergence divergence."),
    "kdj": IndicatorSpec(KDJ, ("Close", "High", "Low"), ("K", "D", "J"), "KDJ stochastic oscillator."),
    "rsi": IndicatorSpec(RSI, ("Close",), ("RSI",), "Relative strength index."),
    "wr": IndicatorSpec(WR, ("Close", "High", "Low"), ("WR", "WR1"), "Williams %R."),
    "bias": IndicatorSpec(BIAS, ("Close",), ("BIAS1", "BIAS2", "BIAS3"), "Price bias versus moving averages."),
    "boll": IndicatorSpec(BOLL, ("Close",), ("UPPER", "MID", "LOWER"), "Bollinger band values."),
    "psy": IndicatorSpec(PSY, ("Close",), ("PSY", "PSYMA"), "Psychological line indicator."),
    "cci": IndicatorSpec(CCI, ("Close", "High", "Low"), ("CCI",), "Commodity channel index."),
    "atr": IndicatorSpec(ATR, ("Close", "High", "Low"), ("ATR",), "Average true range."),
    "bbi": IndicatorSpec(BBI, ("Close",), ("BBI",), "Bull and bear index."),
    "dmi": IndicatorSpec(DMI, ("Close", "High", "Low"), ("PDI", "MDI", "ADX", "ADXR"), "Directional movement index."),
    "taq": IndicatorSpec(TAQ, ("High", "Low"), ("UP", "MID", "DOWN"), "Donchian-style channel."),
    "trix": IndicatorSpec(TRIX, ("Close",), ("TRIX", "TRMA"), "Triple exponential average oscillator."),
    "vr": IndicatorSpec(VR, ("Close", "Volume"), ("VR",), "Volume ratio."),
    "emv": IndicatorSpec(EMV, ("High", "Low", "Volume"), ("EMV", "MAEMV"), "Ease of movement."),
    "dpo": IndicatorSpec(DPO, ("Close",), ("DPO", "MADPO"), "Detrended price oscillator."),
    "brar": IndicatorSpec(BRAR, ("Open", "Close", "High", "Low"), ("AR", "BR"), "AR/BR sentiment indicator."),
    "dma": IndicatorSpec(DMA, ("Close",), ("DIF", "DIFMA"), "Difference of moving averages."),
    "mtm": IndicatorSpec(MTM, ("Close",), ("MTM", "MTMMA"), "Momentum indicator."),
    "roc": IndicatorSpec(ROC, ("Close",), ("ROC", "MAROC"), "Rate of change."),
}


def available_indicators() -> list[str]:
    return sorted(INDICATOR_SPECS.keys())


def _resolve_root_dir(root_dir: str | None = None) -> str:
    if root_dir:
        return root_dir
    config = get_config()
    return str(config.get("data_root", "data/market"))


def _resolve_local_symbol(symbol: str, root_dir: str | None = None) -> str:
    resolved_root = _resolve_root_dir(root_dir)
    candidate = str(symbol or "").strip().upper()
    if not candidate:
        raise ValueError("symbol is required")

    if (Path(resolved_root) / candidate).exists():
        return candidate

    try:
        from activeportfolio.dataflows.ashare import normalize_symbol as normalize_ashare_symbol

        ashare_candidate = normalize_ashare_symbol(symbol)
    except Exception:
        ashare_candidate = candidate

    if (Path(resolved_root) / ashare_candidate).exists():
        return ashare_candidate
    return ashare_candidate


def load_symbol_history(
    symbol: str,
    start_date: str,
    end_date: str,
    root_dir: str | None = None,
) -> pd.DataFrame:
    resolved_root = _resolve_root_dir(root_dir)
    resolved_symbol = _resolve_local_symbol(symbol, root_dir=resolved_root)
    return load_history_window(
        symbol=resolved_symbol,
        start_date=start_date,
        end_date=end_date,
        root_dir=resolved_root,
    )


def calculate_indicator_frame(
    history: pd.DataFrame,
    indicator: str,
    **kwargs,
) -> pd.DataFrame:
    indicator_key = indicator.lower()
    if indicator_key not in INDICATOR_SPECS:
        raise ValueError(
            f"Indicator '{indicator}' is not supported. Choose from: {available_indicators()}"
        )

    spec = INDICATOR_SPECS[indicator_key]
    missing = [column for column in spec.inputs if column not in history.columns]
    if missing:
        raise ValueError(f"History data missing required columns for {indicator_key}: {missing}")

    args = [history[column].to_numpy(dtype=float) for column in spec.inputs]
    values = spec.func(*args, **kwargs)
    if not isinstance(values, tuple):
        values = (values,)

    result = pd.DataFrame({"Date": pd.to_datetime(history["Date"])})
    for column_name, value in zip(spec.outputs, values):
        result[column_name] = np.asarray(value, dtype=float)
    return result


def calculate_indicator_from_parquet(
    symbol: str,
    indicator: str,
    start_date: str,
    end_date: str,
    root_dir: str | None = None,
    **kwargs,
) -> pd.DataFrame:
    history = load_symbol_history(
        symbol=symbol,
        start_date=start_date,
        end_date=end_date,
        root_dir=root_dir,
    )
    return calculate_indicator_frame(history, indicator, **kwargs)


def get_mytt_indicators_window(
    symbol: str,
    indicator: str,
    curr_date: str,
    look_back_days: int,
    root_dir: str | None = None,
) -> str:
    curr_ts = pd.Timestamp(curr_date)
    window_start = (curr_ts - pd.Timedelta(days=look_back_days)).strftime("%Y-%m-%d")
    warmup_start = (curr_ts - pd.Timedelta(days=max(look_back_days + 250, 365))).strftime(
        "%Y-%m-%d"
    )

    history = load_symbol_history(
        symbol=symbol,
        start_date=warmup_start,
        end_date=curr_ts.strftime("%Y-%m-%d"),
        root_dir=root_dir,
    )
    indicator_frame = calculate_indicator_frame(history, indicator)
    indicator_window = indicator_frame[
        (indicator_frame["Date"] >= pd.Timestamp(window_start))
        & (indicator_frame["Date"] <= curr_ts)
    ].copy()

    if indicator_window.empty:
        raise ValueError(
            f"No indicator rows available for symbol '{symbol}' in range {window_start}..{curr_date}"
        )

    indicator_key = indicator.lower()
    output_columns = [column for column in indicator_window.columns if column != "Date"]
    value_map: dict[str, str] = {}
    for _, row in indicator_window.iterrows():
        pieces = []
        for column in output_columns:
            value = row[column]
            formatted = "N/A" if pd.isna(value) else f"{float(value):.3f}"
            pieces.append(f"{column}={formatted}")
        value_map[row["Date"].strftime("%Y-%m-%d")] = ", ".join(pieces)

    lines = []
    current = curr_ts
    boundary = pd.Timestamp(window_start)
    while current >= boundary:
        date_str = current.strftime("%Y-%m-%d")
        lines.append(
            f"{date_str}: {value_map.get(date_str, 'N/A: Not a trading day (weekend or holiday)')}"
        )
        current -= pd.Timedelta(days=1)

    spec = INDICATOR_SPECS[indicator_key]
    resolved_symbol = _resolve_local_symbol(symbol, root_dir=root_dir)
    return (
        f"## {indicator_key} values from {window_start} to {curr_date} for {resolved_symbol}:\n\n"
        + "\n".join(lines)
        + "\n\n"
        + spec.description
    )
