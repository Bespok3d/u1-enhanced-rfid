# Security Policy

Bespok3d installs signed packages onto a networked 3D printer and runs an on-printer daemon that
handles authentication and fleet access, so we take security reports seriously.

## Reporting a vulnerability

Please report security issues privately, not in a public issue or pull request.

Use GitHub's private vulnerability reporting: open this repository's **Security** tab and choose
**Report a vulnerability**. That opens a private advisory only the maintainers can see.

Tell us what you found, how to reproduce it, and what an attacker could do with it. We will
acknowledge your report as quickly as we can and keep you posted while we work on a fix.

## What matters most

Bespok3d runs on stock printer firmware and never flashes custom firmware. The reports we care about
most are:

- a plugin package that can run unintended code on the printer,
- a way to install or activate a package without a valid signature,
- a way to bypass the daemon's authentication or reach a printer that is not yours,
- a way to leave a printer unusable from a remote request.

## Please do not

- open a public issue for a security bug,
- test against a printer or daemon you do not own,
- run denial-of-service or destructive tests against shared infrastructure.
