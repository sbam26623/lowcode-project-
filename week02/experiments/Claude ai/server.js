// Contact form web app: no dependencies, Node 18+.
// Run: node server.js   ->  http://localhost:3000/contact

const http = require("http");

const PORT = process.env.PORT || 3000;
const MAX_BODY_BYTES = 20 * 1024;
const LIMITS = { name: 100, email: 254, message: 5000 };

// Practical email check: local@domain.tld, no spaces, no consecutive dots,
// domain labels of letters/digits/hyphens, TLD of at least 2 letters.
const EMAIL_RE =
  /^[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*\.[A-Za-z]{2,}$/;

function isValidEmail(email) {
  if (email.length > LIMITS.email) return false;
  if (email.includes("..") || email.startsWith(".")) return false;
  const [local] = email.split("@");
  if (!local || local.length > 64 || local.endsWith(".")) return false;
  return EMAIL_RE.test(email);
}

function validate(input) {
  const values = {
    name: String(input.name ?? "").trim(),
    email: String(input.email ?? "").trim(),
    message: String(input.message ?? "").trim(),
  };
  const errors = {};

  if (!values.name) errors.name = "Enter your name.";
  else if (values.name.length > LIMITS.name)
    errors.name = `Keep your name under ${LIMITS.name} characters.`;

  if (!values.email) errors.email = "Enter your email address.";
  else if (!isValidEmail(values.email))
    errors.email = "Enter a valid email address, like name@example.com.";

  if (!values.message) errors.message = "Write a message.";
  else if (values.message.length > LIMITS.message)
    errors.message = `Keep your message under ${LIMITS.message} characters.`;

  return { values, errors };
}

const escapeHtml = (s) =>
  String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

function renderPage({ values = {}, errors = {}, success = null } = {}) {
  const hasErrors = Object.keys(errors).length > 0;

  const field = (id, label, control, error) => `
      <div class="field${error ? " has-error" : ""}">
        <label for="${id}">${label}</label>
        ${control}
        ${error ? `<p class="error" id="${id}-error">${escapeHtml(error)}</p>` : ""}
      </div>`;

  const aria = (id) =>
    errors[id] ? ` aria-invalid="true" aria-describedby="${id}-error"` : "";

  const body = success
    ? `
    <div class="confirmation" role="status">
      <h1>Message sent</h1>
      <p>Thanks, ${escapeHtml(success.name)}. We received your message and will reply to ${escapeHtml(success.email)}.</p>
      <p><a href="/contact">Send another message</a></p>
    </div>`
    : `
    <h1>Contact us</h1>
    <p class="lede">Send us a message and we will get back to you by email.</p>
    ${hasErrors ? `<div class="summary" role="alert">Fix the highlighted fields and send again.</div>` : ""}
    <form method="post" action="/contact" novalidate>
      ${field(
        "name",
        "Name",
        `<input id="name" name="name" type="text" autocomplete="name" maxlength="${LIMITS.name + 50}" value="${escapeHtml(values.name ?? "")}"${aria("name")}>`,
        errors.name
      )}
      ${field(
        "email",
        "Email",
        `<input id="email" name="email" type="email" autocomplete="email" value="${escapeHtml(values.email ?? "")}"${aria("email")}>`,
        errors.email
      )}
      ${field(
        "message",
        "Message",
        `<textarea id="message" name="message" rows="7"${aria("message")}>${escapeHtml(values.message ?? "")}</textarea>`,
        errors.message
      )}
      <button type="submit">Send message</button>
    </form>`;

  return `<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Contact</title>
<style>
  :root {
    --bg: #f7f7f5; --surface: #ffffff; --text: #1d2327; --muted: #5b6670;
    --line: #c9ced3; --accent: #1f4e8c; --error: #b3261e; --error-bg: #fdecea;
    --ok: #1e6b43; --ok-bg: #e8f4ed;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #14181c; --surface: #1c2227; --text: #e8ebee; --muted: #9aa6b0;
      --line: #3a444c; --accent: #7fb0ec; --error: #ff8a80; --error-bg: #3a1f1d;
      --ok: #7fd1a1; --ok-bg: #1a3025;
    }
  }
  * { box-sizing: border-box; }
  body { margin: 0; background: var(--bg); color: var(--text);
    font: 16px/1.55 system-ui, -apple-system, "Segoe UI", Roboto, sans-serif; }
  main { max-width: 36rem; margin: 0 auto; padding: 3rem 1.25rem 4rem; }
  h1 { font-size: 1.75rem; line-height: 1.2; margin: 0 0 .5rem; }
  .lede { color: var(--muted); margin: 0 0 1.75rem; }
  .field { margin-bottom: 1.25rem; }
  label { display: block; font-weight: 600; margin-bottom: .35rem; }
  input, textarea { width: 100%; padding: .65rem .75rem; font: inherit; color: inherit;
    background: var(--surface); border: 1px solid var(--line); border-radius: 6px; }
  textarea { resize: vertical; }
  input:focus-visible, textarea:focus-visible, button:focus-visible, a:focus-visible {
    outline: 3px solid var(--accent); outline-offset: 2px; }
  .has-error input, .has-error textarea { border-color: var(--error); border-width: 2px; }
  .error { color: var(--error); margin: .4rem 0 0; font-size: .95rem; font-weight: 500; }
  .summary { background: var(--error-bg); color: var(--error); border-left: 4px solid var(--error);
    padding: .75rem 1rem; margin-bottom: 1.5rem; border-radius: 4px; font-weight: 500; }
  button { font: inherit; font-weight: 600; padding: .7rem 1.4rem; color: #fff; background: var(--accent);
    border: 0; border-radius: 6px; cursor: pointer; }
  @media (prefers-color-scheme: dark) { button { color: #0d1620; } }
  button:hover { filter: brightness(1.1); }
  .confirmation { background: var(--ok-bg); border-left: 4px solid var(--ok);
    padding: 1.25rem 1.5rem; border-radius: 4px; }
  .confirmation h1 { color: var(--ok); }
  a { color: var(--accent); }
</style>
</head>
<body>
<main>${body}
</main>
</body>
</html>`;
}

function send(res, status, html, extraHeaders = {}) {
  res.writeHead(status, {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff",
    "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'",
    ...extraHeaders,
  });
  res.end(html);
}

function readForm(req) {
  return new Promise((resolve, reject) => {
    let size = 0;
    const chunks = [];
    req.on("data", (chunk) => {
      size += chunk.length;
      if (size > MAX_BODY_BYTES) {
        reject(Object.assign(new Error("Payload too large"), { status: 413 }));
        req.destroy();
        return;
      }
      chunks.push(chunk);
    });
    req.on("end", () => {
      const params = new URLSearchParams(Buffer.concat(chunks).toString("utf8"));
      resolve(Object.fromEntries(params));
    });
    req.on("error", reject);
  });
}

const server = http.createServer(async (req, res) => {
  const { pathname } = new URL(req.url, "http://localhost");

  if (pathname === "/") {
    res.writeHead(302, { Location: "/contact" });
    return res.end();
  }

  if (pathname === "/contact") {
    if (req.method === "GET" || req.method === "HEAD") {
      return send(res, 200, renderPage());
    }
    if (req.method === "POST") {
      try {
        const type = req.headers["content-type"] || "";
        if (!type.startsWith("application/x-www-form-urlencoded")) {
          return send(res, 415, "<h1>Unsupported content type</h1>");
        }
        const { values, errors } = validate(await readForm(req));
        if (Object.keys(errors).length) {
          return send(res, 422, renderPage({ values, errors }));
        }
        // Nothing is stored or sent yet. Add persistence or email delivery here.
        return send(res, 200, renderPage({ success: values }));
      } catch (err) {
        return send(res, err.status || 500, `<h1>${err.status === 413 ? "Message too large" : "Something went wrong"}</h1>`);
      }
    }
    return send(res, 405, "<h1>Method not allowed</h1>", { Allow: "GET, HEAD, POST" });
  }

  send(res, 404, "<h1>Not found</h1>");
});

server.listen(PORT, () => console.log(`Contact form running at http://localhost:${PORT}/contact`));

module.exports = { validate, isValidEmail };
