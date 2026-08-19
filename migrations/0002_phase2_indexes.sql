CREATE INDEX jobs_runnable_idx ON jobs(run_id, kind, status, deadline_at);
CREATE INDEX events_aggregate_idx ON semantic_events(aggregate_id, sequence);
CREATE INDEX proposals_run_idx ON proposals(run_id, proposal_id);
CREATE INDEX model_calls_run_idx ON model_calls(run_id, call_id);
