# TikTok Factory Architecture

This first version is intentionally flat so it can be uploaded from a phone.

GitHub Actions runs the editorial collector while the PC is off.

It reads public RSS feeds, scores candidates, removes duplicates and creates JSON jobs in the repository root.

A future Windows worker will pull jobs beginning with `job_` and send them to MoneyPrinterTurbo.

This is a reliable zero-paid-API foundation, not an LLM researcher yet.

An intelligence layer can later enrich the scripts using a local model or another allowed/free provider without changing the job contract.

Automatic TikTok publishing is intentionally disabled until video quality is validated.
