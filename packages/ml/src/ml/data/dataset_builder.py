from __future__ import annotations

import argparse
import time
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    from influxdb_client import InfluxDBClient
except ImportError as exc:
    raise SystemExit(
        "Missing dependency 'influxdb-client'. Install it with `uv add influxdb-client --project packages/ml`."
    ) from exc


INFLUX_URL = "http://192.168.3.14:8086"
INFLUX_TOKEN = "pf-OGC6AQFmKy64gOzRM12DZrCuavnWeMgRZ2kDMOk8LYK22evDJnoyKGcmY49EgT8HnMDE9GPQeg30vXeHsRQ=="
INFLUX_ORG = "belimo"
INFLUX_BUCKET = "actuator-data"
INFLUX_MEASUREMENT = "measurements"


def _safe_name(value: str) -> str:
    cleaned = value.strip()
    if not cleaned:
        return "session"
    return "".join(char if char.isalnum() else "_" for char in cleaned)


def _normalize_query_result(
    frame_or_frames: pd.DataFrame | list[pd.DataFrame],
) -> pd.DataFrame:
    if isinstance(frame_or_frames, list):
        frames = [frame for frame in frame_or_frames if not frame.empty]
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)
    return frame_or_frames


def _build_query(bucket: str, measurement: str, lookback_seconds: int) -> str:
    return f"""
        from(bucket:"{bucket}")
        |> range(start: -{lookback_seconds}s)
        |> filter(fn: (r) => r["_measurement"] == "{measurement}")
        |> pivot(rowKey:["_time"], columnKey: ["_field"], valueColumn: "_value")
        |> drop(columns: ["_start", "_stop"])
    """


def build_dataset(recordings_dir: Path, output_path: Path, pattern: str) -> int:
    files = sorted(recordings_dir.glob(pattern))
    frames: list[pd.DataFrame] = []

    for file_path in files:
        if file_path.resolve() == output_path.resolve():
            continue

        try:
            frame = pd.read_csv(file_path)
        except Exception as exc:
            print(f"Skipping {file_path.name}: {exc}")
            continue

        if frame.empty:
            continue

        if "anomaly_type" not in frame.columns:
            frame["anomaly_type"] = "unknown"
        frame["anomaly_type"] = frame["anomaly_type"].fillna("unknown").astype(str)

        if "is_anomaly" not in frame.columns:
            frame["is_anomaly"] = 0
        frame["is_anomaly"] = (
            pd.to_numeric(frame["is_anomaly"], errors="coerce")
            .fillna(0)
            .clip(lower=0, upper=1)
            .astype(int)
        )

        if "recording_event" not in frame.columns:
            frame["recording_event"] = file_path.stem

        frame["source_file"] = file_path.name
        frames.append(frame)

    if not frames:
        raise ValueError(
            f"No non-empty CSV recordings found in {recordings_dir} for pattern '{pattern}'."
        )

    dataset = pd.concat(frames, ignore_index=True)

    if "_time" in dataset.columns:
        dataset["_time"] = pd.to_datetime(dataset["_time"], errors="coerce", utc=True)
        dataset = dataset.sort_values(by="_time")

    dedupe_cols = [col for col in ("_time", "source_file") if col in dataset.columns]
    if dedupe_cols:
        dataset = dataset.drop_duplicates(subset=dedupe_cols, keep="last")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    dataset.to_csv(output_path, index=False)

    print(f"Built dataset at {output_path} with {len(dataset)} rows.")
    counts = dataset["is_anomaly"].value_counts().to_dict()
    print(f"is_anomaly distribution: {counts}")
    type_counts = dataset["anomaly_type"].value_counts().to_dict()
    print(f"anomaly_type distribution: {type_counts}")
    return len(dataset)


def collect_session(args: argparse.Namespace) -> Path:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_event_name = _safe_name(args.event_name)
    safe_anomaly_type = _safe_name(args.anomaly_type)
    filename = output_dir / f"{safe_event_name}__{safe_anomaly_type}__{stamp}.csv"

    print(f"Starting labeled recording for event '{args.event_name}'")
    print(
        f"Anomaly label: anomaly_type='{args.anomaly_type}', is_anomaly={args.is_anomaly}"
    )
    print(f"Streaming telemetry to {filename}")
    print("Press CTRL-C to stop recording.\n")

    client = InfluxDBClient(
        url=args.url,
        token=args.token,
        org=args.org,
        verify_ssl=False,
    )
    query_api = client.query_api()

    headers_written = False
    total_rows = 0
    last_seen_time: pd.Timestamp | None = None

    try:
        while True:
            query = _build_query(
                bucket=args.bucket,
                measurement=args.measurement,
                lookback_seconds=args.window_seconds,
            )

            try:
                frame = _normalize_query_result(query_api.query_data_frame(query))

                if not frame.empty and "_time" in frame.columns:
                    frame["_time"] = pd.to_datetime(
                        frame["_time"], errors="coerce", utc=True
                    )
                    frame = frame.dropna(subset=["_time"]).sort_values(by="_time")

                    if last_seen_time is not None:
                        frame = frame[frame["_time"] > last_seen_time]

                    if args.test_number is not None and "test_number" in frame.columns:
                        test_number_values = pd.to_numeric(
                            frame["test_number"], errors="coerce"
                        )
                        frame = frame[test_number_values == args.test_number]

                    if not frame.empty:
                        last_seen_time = frame["_time"].max()
                        frame.drop(
                            columns=["result", "table"], errors="ignore", inplace=True
                        )

                        frame["recording_event"] = args.event_name
                        frame["anomaly_type"] = args.anomaly_type
                        frame["is_anomaly"] = int(args.is_anomaly)

                        mode = "a" if headers_written else "w"
                        frame.to_csv(
                            filename,
                            mode=mode,
                            header=not headers_written,
                            index=False,
                        )
                        headers_written = True

                        new_rows = len(frame)
                        total_rows += new_rows
                        clock = datetime.now().strftime("%H:%M:%S")
                        print(
                            f"[{clock}] Appended {new_rows} rows (Total: {total_rows})"
                        )

            except Exception as exc:
                print(f"Error fetching chunk: {exc}")

            time.sleep(args.poll_seconds)

    except KeyboardInterrupt:
        print("\nCTRL-C detected. Stopping stream...")
    finally:
        client.close()
        print(f"Finished. Saved {total_rows} rows to {filename}.")

    if args.rebuild_dataset:
        dataset_rows = build_dataset(
            recordings_dir=output_dir,
            output_path=Path(args.dataset_path),
            pattern=args.pattern,
        )
        print(f"Rebuilt combined dataset with {dataset_rows} rows.")

    return filename


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Collect labeled telemetry sessions and build a dataset for anomaly detection."
        )
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    collect_parser = subparsers.add_parser(
        "collect",
        help="Collect one labeled recording session from InfluxDB.",
    )
    collect_parser.add_argument(
        "event_name",
        type=str,
        help="Human-readable recording name (saved to recording_event).",
    )
    collect_parser.add_argument(
        "--anomaly-type",
        type=str,
        default="normal",
        help="Label for anomaly_type column, e.g. normal or stiction_suspected.",
    )
    collect_parser.add_argument(
        "--is-anomaly",
        type=int,
        choices=[0, 1],
        default=0,
        help="Binary label for is_anomaly column (0 or 1).",
    )
    collect_parser.add_argument(
        "--url",
        type=str,
        default=INFLUX_URL,
        help="InfluxDB URL.",
    )
    collect_parser.add_argument(
        "--token",
        type=str,
        default=INFLUX_TOKEN,
        help="InfluxDB token.",
    )
    collect_parser.add_argument(
        "--org",
        type=str,
        default=INFLUX_ORG,
        help="InfluxDB organization.",
    )
    collect_parser.add_argument(
        "--bucket",
        type=str,
        default=INFLUX_BUCKET,
        help="InfluxDB bucket.",
    )
    collect_parser.add_argument(
        "--measurement",
        type=str,
        default=INFLUX_MEASUREMENT,
        help="Measurement to read from (usually 'measurements').",
    )
    collect_parser.add_argument(
        "--test-number",
        type=int,
        default=None,
        help="Optional filter to keep rows where test_number equals this value.",
    )
    collect_parser.add_argument(
        "--output-dir",
        type=str,
        default="ml/data/processed/recordings",
        help="Directory where session CSV files are saved.",
    )
    collect_parser.add_argument(
        "--window-seconds",
        type=int,
        default=5,
        help="Query lookback window in seconds.",
    )
    collect_parser.add_argument(
        "--poll-seconds",
        type=float,
        default=1.0,
        help="Polling interval in seconds.",
    )
    collect_parser.add_argument(
        "--rebuild-dataset",
        action="store_true",
        help="Rebuild combined dataset after stopping recording.",
    )
    collect_parser.add_argument(
        "--dataset-path",
        type=str,
        default="ml/data/processed/anomaly_dataset.csv",
        help="Where to write the combined dataset when --rebuild-dataset is used.",
    )
    collect_parser.add_argument(
        "--pattern",
        type=str,
        default="*.csv",
        help="File pattern used when rebuilding the dataset.",
    )

    build_parser = subparsers.add_parser(
        "build",
        help="Build one combined CSV dataset from recorded sessions.",
    )
    build_parser.add_argument(
        "--recordings-dir",
        type=str,
        default="ml/data/processed/recordings",
        help="Directory containing recording CSV files.",
    )
    build_parser.add_argument(
        "--pattern",
        type=str,
        default="*.csv",
        help="File glob pattern to include recordings.",
    )
    build_parser.add_argument(
        "--output",
        type=str,
        default="ml/data/processed/anomaly_dataset.csv",
        help="Path to write the combined dataset CSV.",
    )

    return parser


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()

    if args.command == "collect":
        if args.window_seconds <= 0:
            raise SystemExit("--window-seconds must be greater than 0.")
        if args.poll_seconds <= 0:
            raise SystemExit("--poll-seconds must be greater than 0.")
        collect_session(args)
        return

    if args.command == "build":
        build_dataset(
            recordings_dir=Path(args.recordings_dir),
            output_path=Path(args.output),
            pattern=args.pattern,
        )
        return

    raise SystemExit(f"Unsupported command: {args.command}")


if __name__ == "__main__":
    main()
