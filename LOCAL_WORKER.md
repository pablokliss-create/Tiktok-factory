# Local Worker Contract

The future Windows worker should:

1. Pull the repository.
2. Find root-level `job_*.json` files with status `queued`.
3. Hand selected jobs to MoneyPrinterTurbo.
4. Generate the video.
5. Run local QA.
6. Only after successful QA mark a job ready for publishing.
7. Keep failed jobs available for inspection.

The worker should default to a D: drive path.
