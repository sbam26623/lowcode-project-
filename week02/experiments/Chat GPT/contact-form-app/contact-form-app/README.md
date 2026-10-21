# Northstar Contact Form

A small Express web app with a contact page at `/contact`.

## Requirements
- Node.js 18+

## Run locally
```bash
npm install
npm start
```
Open http://localhost:3000/contact

## Behaviour
- Name and message are trimmed and rejected when empty.
- Email syntax is checked on the server for a basic well-formed address.
- Invalid submissions return the form with visible, field-specific errors.
- Valid submissions show an on-page confirmation.
- Submissions are **not stored, logged, emailed, or persisted**.
- Browser validation is a usability aid only; server-side checks remain authoritative.

The email check validates format only. It does not confirm that the mailbox exists.
