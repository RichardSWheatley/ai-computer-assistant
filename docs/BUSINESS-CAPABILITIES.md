# Business Capabilities

The assistant isn't just for coding — it's a full **business co-worker**. This
covers the Microsoft 365 stack: Teams, Outlook, Calendar, and PowerPoint, plus
Word/Excel and file storage.

> **Golden rule:** prefer the **Microsoft Graph API** over GUI automation. The
> API is faster, reliable, and auditable. Only drive the desktop app's UI when
> no API exists (e.g. niche formatting).

## 1. Microsoft Teams 💬

| Task | How |
|---|---|
| Read channel & chat messages | Graph `chats` / `teams` endpoints |
| Post / reply to messages | Graph `chatMessage` create |
| Summarize a channel or thread | Fetch messages → LLM summary |
| Schedule / join meetings | Graph `onlineMeetings` + Calendar |
| @mention and notify people | Graph message with mentions |
| Draft a status update from your git activity | Dev toolkit → LLM → post |

**Examples**
- "Summarize what I missed in the #backend channel today."
- "Post the release notes to the team and @mention the QA lead."

## 2. Outlook email ✉️

| Task | How |
|---|---|
| Triage inbox (label, prioritize, summarize) | Graph `messages` + LLM |
| Draft a new email in your voice | LLM + your style profile (memory) |
| Reply / reply-all with context | Graph thread fetch → draft → **confirm** → send |
| Search mail | Graph search |
| Extract action items / attachments | LLM over message bodies |

**Safety:** sending mail is outward-facing → the assistant **drafts first and
asks for confirmation** before sending, unless you pre-authorize a sender/flow.

**Examples**
- "Draft a reply to the client thread proposing Thursday and attach the spec."
- "Clear my inbox: summarize, label, and draft responses to anything urgent."

## 3. Calendar & scheduling 📅

- Find free times across attendees, propose slots, create/update/cancel events,
  respond to invites, set reminders. Graph `calendar` + `findMeetingTimes`.
- **Example:** "Find 30 minutes with Sam and Priya next week and send an invite."

## 4. PowerPoint — decks with *immense graphics* 📊

This is a flagship feature. The pipeline:

```
brief ──▶ outline (LLM) ──▶ slide plan ──▶ layout + content ──▶ graphics ──▶ .pptx
```

1. **Outline & narrative** — LLM turns a prompt or source doc into a structured
   story (title, agenda, key messages, takeaways).
2. **Layout engine** — branded master templates: title, section, two-column,
   comparison, big-number, quote, closing.
3. **Graphics pipeline (the "immense graphics")**:
   - **Charts** from data (native PPTX charts or rendered images).
   - **Diagrams** — flows, architectures, timelines, org charts.
   - **Icons & illustrations** — curated icon sets, consistent style.
   - **AI-generated imagery** — hero images, backgrounds, concept art via an
     image model, on-brand and high-resolution.
   - **Smart layout** — alignment, spacing, color palette, and typography rules
     so it looks designed, not auto-generated.
4. **Assembly** — `python-pptx` writes the real editable `.pptx` (shapes, charts,
   images, speaker notes). Output is a normal PowerPoint file you can tweak.

**Examples**
- "Build a 12-slide Q3 board deck from this spreadsheet — charts, a roadmap
   timeline, and a strong hero image on the title."
- "Turn this design doc into a customer-facing pitch with diagrams."

## 5. Word & Excel 📄

- **Word**: reports, proposals, specs, meeting minutes (`python-docx`).
- **Excel**: read/write workbooks, build tables, formulas, charts, pivot-style
  summaries (`openpyxl`), or via Graph for files in OneDrive/SharePoint.

## 6. Files: OneDrive / SharePoint 🗂️

- Search, read, create, move, and share documents via Graph. Pull source
  material for decks/emails and save outputs back to the right folder.

## 7. End-to-end business workflows 🔗

Where it really shines — chaining the above:

- **"Prep me for the 9am."** → read the calendar event, pull the related email
  thread + Teams chat + attached docs, summarize, and draft talking points.
- **"Follow up after the meeting."** → take notes, extract action items, draft
  the recap email, post a summary to Teams, and create calendar holds for the
  next steps.
- **"Monthly report."** → pull data from Excel/SharePoint → build the Word
  report and the PPTX deck → draft the email to leadership for your approval.

## Auth & setup notes

- Uses **Microsoft Graph** with OAuth (delegated permissions) — the assistant
  acts as *you*, with only the scopes you grant.
- Tokens live in the OS credential vault; least-privilege scopes per feature.
- Every outward action (send mail, post to Teams, share a file) is gated by the
  permission tier in [ARCHITECTURE.md](ARCHITECTURE.md#4-security--safety-model).
