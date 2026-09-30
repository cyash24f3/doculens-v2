# Data export procedure

## Permissions

Only workspace administrators can request a full workspace export. Members can export individual documents they can read.

## Format

Workspace exports contain UTF-8 JSON metadata and Markdown content in a ZIP archive. Attachments are stored in a separate folder.

## Expiry

Download links expire 48 hours after the export is ready. Expired exports must be requested again.

## Retention

Generated export archives are deleted from the download service after 7 days. Original workspace content is unaffected.

## Size

Exports larger than 2 GB are split into numbered archives. Download all parts before attempting extraction.

## Read-only snapshot

An export captures content at request time. Changes made after the request are not included in that archive.
