import json
import logging
import os
import subprocess
from datetime import datetime
from typing import List, Dict, Any, Optional

def parse_log_line(line: str) -> Optional[Dict[str, Any]]:
    """
    Parses a single line from grok.log.
    Format: 2026-02-02 13:26:17,393 - INFO - {"event": "STARTUP", ...}
    """
    try:
        parts = line.split(" - ", 2)
        if len(parts) < 3:
            # Maybe it's a non-structured line
            return None
        
        timestamp_str = parts[0].strip()
        level = parts[1].strip()
        json_payload_str = parts[2].strip()
        
        try:
            payload = json.loads(json_payload_str)
        except json.JSONDecodeError:
            # Not a JSON payload, return as raw message
            return {
                "timestamp": timestamp_str,
                "level": level,
                "event": "RAW",
                "message": json_payload_str
            }
        
        return {
            "timestamp": timestamp_str,
            "level": level,
            **payload
        }
    except Exception:
        return None

def tail_log_file(path: str, num_lines: int = 1000) -> List[Dict[str, Any]]:
    """
    Reads the last N lines of a log file and parses them.
    This implementation uses a native OS tail command to scale to GB-sized logs without OOMing the server.
    """
    if not os.path.exists(path):
        return []
    
    parsed_lines = []
    try:
        # Efficiently read the end of the large file using native tail
        output = subprocess.check_output(["tail", "-n", str(num_lines), path]).decode('utf-8', errors='replace')
        for line in output.splitlines():
            parsed = parse_log_line(line)
            if parsed:
                parsed_lines.append(parsed)
    except Exception as e:
        logging.error(f"Error reading log file {path}: {e}")
    
    return parsed_lines

def categorize_logs(logs: List[Dict[str, Any]]) -> Dict[str, List[Dict[str, Any]]]:
    """
    Categorizes logs into different groups based on event type.
    """
    categories = {
        "ALERT": [],
        "MARKET": [],
        "SYSTEM": [],
        "ERROR": [],
        "ALL": logs
    }
    
    market_events = {"BOOK_SUMMARY", "ROLL", "IMBALANCE_DEBUG", "VOLUME_FALLBACK", "PRICE_FALLBACK"}
    system_events = {"STARTUP", "CLIENT_INIT", "HEARTBEAT", "INSTR_DEBUG"}
    error_events = {"SUBS_ERROR", "L2_ERROR", "L1_ERROR", "CHART_ERROR", "TIMESALE_ERROR", "INSTR_ERROR"}
    
    for log in logs:
        event = log.get("event", "RAW")
        if event == "ALERT":
            categories["ALERT"].append(log)
        elif event in market_events:
            categories["MARKET"].append(log)
        elif event in system_events:
            categories["SYSTEM"].append(log)
        elif event in error_events or log.get("level") in {"ERROR", "CRITICAL", "WARNING"}:
            categories["ERROR"].append(log)
            
    return categories
