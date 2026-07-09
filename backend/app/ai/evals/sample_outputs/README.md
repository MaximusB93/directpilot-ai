# Saved AI Outputs

This directory stores static, already-saved AI responses for offline scoring.

The offline eval runner never calls OpenRouter, never requires API keys, and never writes
to production data. Add a subdirectory per model or prompt baseline, for example:

```text
sample_outputs/
  baseline_v1/
    001_high_cpa.json
```

Each JSON file should include `case_id`, model metadata, task name, and a `response`
object that can be scored against the corresponding eval case.
