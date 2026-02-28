import io
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pandas as pd

from tradingagents.dataflows.y_finance import get_YFin_data_online


class TestYFinanceHistoryDownload(unittest.TestCase):
    def test_download_history_for_requested_tickers(self) -> None:
        tickers = ["SPY", "TSLA", "AAPL", "TLT", "GLD"]
        start_date = "2020-01-01"
        # yfinance treats end as exclusive; +1 day ensures latest available bar is included.
        end_date = (datetime.now(timezone.utc) + timedelta(days=1)).strftime("%Y-%m-%d")
        output_dir = Path("data/unittest")
        output_dir.mkdir(parents=True, exist_ok=True)

        for ticker in tickers:
            with self.subTest(ticker=ticker):
                result = get_YFin_data_online(ticker, start_date, end_date)

                self.assertIsInstance(result, str)
                self.assertNotIn("No data found for symbol", result)
                self.assertIn(f"# Stock data for {ticker}", result)
                self.assertIn("# Total records:", result)

                csv_lines = [
                    line
                    for line in result.splitlines()
                    if line and not line.startswith("#")
                ]
                df = pd.read_csv(io.StringIO("\n".join(csv_lines)))

                self.assertFalse(df.empty)
                self.assertIn("Date", df.columns)
                self.assertIn("Close", df.columns)
                self.assertGreaterEqual(pd.to_datetime(df["Date"]).max(), pd.Timestamp(start_date))

                output_file = output_dir / f"{ticker}_{start_date}_to_latest.csv"
                df.to_csv(output_file, index=False)


if __name__ == "__main__":
    unittest.main()
