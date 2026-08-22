"""Pretty-print an analysis JSON file for human review.

Usage: python services/backend/examples/inspect.py /tmp/test2.json
"""
import json
import sys

path = sys.argv[1] if len(sys.argv) > 1 else "/tmp/analysis-live.json"
with open(path) as analysis_file:
    d = json.load(analysis_file)

v = d["video"]
print(f"VIDEO: {v['url']}")
print(f"  range: {v['analyzed_start_ms']}-{v['analyzed_end_ms']}ms  "
      f"source: {v['source_width']}x{v['source_height']}")
ft = d["full_transcript"]
print(f"\nTRANSCRIPT ({len(ft['verbatim_text'])} chars, {len(ft['segments'])} segments):")
print(f"  \"{ft['verbatim_text'][:300]}\"")

total = sum(len(s["actions"]) for s in d["steps"])
print(f"\nSTEPS: {len(d['steps'])}   TOTAL ACTIONS: {total}")
print(f"SCENE REVIEW (2nd model): {'yes' if d.get('scene_review') else 'no (skipped for YouTube)'}")

for s in d["steps"]:
    print(f"\n── Step '{s['step_id']}' [{s['start_ms']}-{s['end_ms']}ms] "
          f"— {len(s['actions'])} action(s)")
    print(f"   goal:      {s['goal']}")
    print(f"   narration: {s['narration']}")
    for a in s["actions"]:
        cs, ce = a.get("cursor_start"), a.get("cursor_end")
        pos = f"({cs['x']},{cs['y']})->({ce['x']},{ce['y']})" if cs and ce else "n/a"
        print(f"     #{a['sequence']} {a['timestamp_ms']}ms {a['action_type']:11s} "
              f"target={a['target_label']!r:20s} cursor={pos:24s} "
              f"src={a['position_source']:8s} conf={a['confidence']}")
    for u in s.get("uncertainties", []):
        print(f"   ! uncertainty: {u}")
