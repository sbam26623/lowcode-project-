const express = require("express");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(express.urlencoded({ extended: false, limit: "20kb" }));
app.use(express.static(path.join(__dirname, "public")));

function isWellFormedEmail(value) {
  // Practical format check: one @, non-empty local/domain parts, and a dotted domain.
  // This checks syntax only; it does not verify that the mailbox exists.
  if (typeof value !== "string" || value.length > 254) return false;
  const email = value.trim();
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

app.get("/contact", (_req, res) => {
  res.sendFile(path.join(__dirname, "public", "contact.html"));
});

app.post("/contact", (req, res) => {
  const name = typeof req.body.name === "string" ? req.body.name.trim() : "";
  const email = typeof req.body.email === "string" ? req.body.email.trim() : "";
  const message = typeof req.body.message === "string" ? req.body.message.trim() : "";

  const errors = {};
  if (!name) errors.name = "Please enter your name.";
  if (!email) errors.email = "Please enter your email address.";
  else if (!isWellFormedEmail(email)) errors.email = "Please enter a valid email address.";
  if (!message) errors.message = "Please enter a message.";

  if (Object.keys(errors).length) {
    return res.status(400).send(renderForm({ name, email, message, errors }));
  }

  // Intentionally do not store, log, email, or otherwise persist submissions.
  return res.status(200).send(renderSuccess());
});

function escapeHtml(value = "") {
  return String(value).replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
  })[char]);
}

function renderForm({ name = "", email = "", message = "", errors = {}, notice = "" } = {}) {
  const fieldError = (key) => errors[key]
    ? `<p class="field-error" id="${key}-error">${escapeHtml(errors[key])}</p>` : "";
  const invalid = (key) => errors[key] ? ` aria-invalid="true" aria-describedby="${key}-error"` : "";
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contact us</title><link rel="stylesheet" href="/styles.css"></head>
<body><main class="shell"><a class="brand" href="/contact"><span class="brand-mark">N</span> northstar<span class="brand-dot">.</span></a>
<section class="contact-layout"><div class="intro"><p class="eyebrow">LET'S TALK</p><h1>Good things start with a hello.</h1><p class="lede">Have a question, an idea, or just want to say hi? Send us a note and we’ll take it from there.</p>
<div class="aside-note"><span class="note-icon">✳</span><div><strong>A real conversation,</strong><br><span>without the complicated stuff.</span></div></div>
<div class="decorative-line"></div><p class="small-note">We’re glad you’re here.</p></div>
<div class="form-panel"><div class="panel-heading"><h2>Get in touch</h2><p>Fill out the form below and share what’s on your mind.</p></div>
${notice ? `<div class="notice" role="alert">${escapeHtml(notice)}</div>` : ""}
<form action="/contact" method="post" novalidate>
<div class="field"><label for="name">Your name <span>*</span></label><input id="name" name="name" type="text" autocomplete="name" placeholder="e.g. Alex Morgan" value="${escapeHtml(name)}"${invalid("name")}>${fieldError("name")}</div>
<div class="field"><label for="email">Email address <span>*</span></label><input id="email" name="email" type="text" inputmode="email" autocomplete="email" placeholder="alex@example.com" value="${escapeHtml(email)}"${invalid("email")}>${fieldError("email")}</div>
<div class="field"><label for="message">Message <span>*</span></label><textarea id="message" name="message" rows="5" placeholder="Tell us a little about what you need..."${invalid("message")}>${escapeHtml(message)}</textarea>${fieldError("message")}</div>
<button type="submit">Send message <span aria-hidden="true">↗</span></button><p class="privacy-note"><span aria-hidden="true">◇</span> Your message is validated but not saved.</p>
</form></div></section><footer><span>© ${new Date().getFullYear()} Northstar Studio</span><span>Made for meaningful conversations.</span></footer></main></body></html>`;
}

function renderSuccess() {
  return `<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>Message confirmed</title><link rel="stylesheet" href="/styles.css"></head>
<body><main class="shell"><a class="brand" href="/contact"><span class="brand-mark">N</span> northstar<span class="brand-dot">.</span></a>
<section class="success-wrap"><div class="success-icon" aria-hidden="true">✓</div><p class="eyebrow">MESSAGE RECEIVED</p><h1>Thanks for reaching out.</h1><p class="lede">Your form passed validation. This demo doesn’t save or send submissions, so nothing has been stored.</p><a class="back-link" href="/contact">← Back to contact form</a></section>
<footer><span>© ${new Date().getFullYear()} Northstar Studio</span><span>Made for meaningful conversations.</span></footer></main></body></html>`;
}

app.listen(PORT, () => {
  console.log(`Contact form app running at http://localhost:${PORT}/contact`);
});
