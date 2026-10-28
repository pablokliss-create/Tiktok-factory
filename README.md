# TikTok Factory

Zero-paid-API editorial queue for a TikTok content factory.

This temporary flat version keeps every project file in the repository root so it can be uploaded easily from a phone.

GitHub Actions researches public RSS feeds while the PC is offline, scores and deduplicates topics, and writes queue jobs as JSON files in the repository root.

The future Windows worker can pull these jobs and hand them to MoneyPrinterTurbo.

## MVP
- No paid LLM/API required
- Public RSS feeds
- Deterministic scoring and deduplication
- Scheduled + manual GitHub Actions
- JSON jobs ready for a local production worker
- Automatic TikTok posting disabled initially
