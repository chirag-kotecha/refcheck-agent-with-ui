const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, ImageRun,
  AlignmentType, LevelFormat, BorderStyle, TableOfContents, PageBreak,
  Table, TableRow, TableCell, WidthType, ShadingType,
} = require("docx");
const fs = require("fs");

const DIAG = "/home/claude/refcheck-agent/docs/diagrams";
const OUT = "/home/claude/refcheck-agent/docs/build/Reference_Check_Analyzer_Business_Overview.docx";

const US_LETTER = { width: 12240, height: 15840 };
const NAVY = "1F3864";
const ACCENT = "5B84B1";
const GREY = "595959";

function h1(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_1, spacing: { before: 360, after: 160 } });
}
function h2(text) {
  return new Paragraph({ text, heading: HeadingLevel.HEADING_2, spacing: { before: 260, after: 120 } });
}
function body(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, ...opts })],
    spacing: { after: 160 },
  });
}
function bullet(text, level = 0) {
  return new Paragraph({
    text,
    numbering: { reference: "bullets", level },
    spacing: { after: 80 },
  });
}
function caption(text) {
  return new Paragraph({
    children: [new TextRun({ text, italics: true, size: 20, color: GREY })],
    alignment: AlignmentType.CENTER,
    spacing: { after: 300 },
  });
}
function image(path, widthPx) {
  const dims = widthPx || 600;
  return new Paragraph({
    children: [
      new ImageRun({
        type: "png",
        data: fs.readFileSync(path),
        transformation: { width: dims, height: Math.round(dims * 0.55) },
      }),
    ],
    alignment: AlignmentType.CENTER,
    spacing: { before: 120, after: 60 },
  });
}
function hr() {
  return new Paragraph({
    text: "",
    border: { bottom: { color: "AAAAAA", space: 1, style: BorderStyle.SINGLE, size: 6 } },
    spacing: { after: 200 },
  });
}

const doc = new Document({
  numbering: {
    config: [
      {
        reference: "bullets",
        levels: [
          { level: 0, format: LevelFormat.BULLET, text: "\u2022", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 360, hanging: 260 } } } },
          { level: 1, format: LevelFormat.BULLET, text: "\u25E6", alignment: AlignmentType.LEFT,
            style: { paragraph: { indent: { left: 720, hanging: 260 } } } },
        ],
      },
    ],
  },
  sections: [
    {
      properties: { page: { size: US_LETTER, margin: { top: 1080, bottom: 1080, left: 1260, right: 1260 } } },
      children: [
        new Paragraph({
          children: [new TextRun({ text: "Reference Check Analyzer", bold: true, size: 56, color: NAVY })],
          spacing: { after: 80 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "Business Overview", size: 32, color: ACCENT })],
          spacing: { after: 40 },
        }),
        new Paragraph({
          children: [new TextRun({ text: "Automated reference verification -- what it does, how it fits into hiring, and what stays a human decision.", italics: true, size: 22, color: GREY })],
          spacing: { after: 400 },
        }),
        hr(),

        h1("Executive Summary"),
        body("Checking a candidate's references today is manual: a recruiter or background-check analyst reads a call transcript, an email, or a verification form, and compares it by eye against what the candidate claimed on their application -- title, dates, company, performance. This tool automates that comparison step. It reads every reference the same way a careful analyst would, flags anything that doesn't line up, and produces a clear report in seconds instead of the time it takes a person to read, compare, and write up each reference by hand."),
        body("It does not replace the hiring decision, and it does not replace human judgment on anything ambiguous -- it decides what's clean enough to move forward automatically, and routes anything uncertain to a person, with the specific concern already identified for them."),

        h1("The Problem Today"),
        bullet("Reading and comparing reference call notes or emails against a resume is slow and repetitive -- the same few checks (does the title match, do the dates match, does the company match) get done by hand every single time."),
        bullet("It's easy to miss something when reading quickly, especially subtle things -- a hesitant answer, a title that's technically different but sounds close enough, a reference who avoids answering a question directly."),
        bullet("When a candidate has multiple references, comparing them against each other (not just against the resume) is extra work that often gets skipped -- but it's exactly where real problems can hide: one manager says top performer, a direct report describes a very different experience."),
        bullet("Reference checks that use a mix of formats -- a phone call for one reference, a short online verification form for another -- don't get handled consistently."),

        h1("How It Works"),
        body("At a high level, the process is the same whether a reference comes in as a phone-call summary, an email, or a short form:"),
        image(`${DIAG}/business_flow.png`, 620),
        caption("Figure 1. End-to-end flow, from submission to either an automatic clean report or a flagged review."),
        body("The system reads what each reference actually said, compares it against what the candidate claimed, and only involves a person when something is worth their attention -- a mismatch, a vague or hesitant answer, or references that contradict each other."),

        h1("Two Ways a Reference Can Come In"),
        body("Not every reference check happens the same way, so the tool supports both of the common formats without the recruiter needing to do anything differently:"),
        h2("Open-text reference (a call or an email)"),
        body("The reference talks freely -- a transcript from a phone call, or an email reply. The system reads the free text, pulls out what was actually said about title, dates, company, and tone, and compares that to the candidate's claims."),
        h2("Yes/No verification form"),
        body("Some references come back as a short structured form instead -- confirm the title (yes/no/unsure), confirm the dates, confirm the company, would they rehire, any performance concerns -- often used by HR-mediated verification services. Since the answers are already structured, the system compares them directly; if the reference adds free-text comments, those get read the same way an open-text reference would."),
        body("A candidate can have a mix of both -- for example, a former manager gives a phone reference while HR at the same company returns a structured verification form. Both feed into the same overall report."),

        h1("What Happens When Something Looks Off"),
        body("Three different things can trigger a human review, and the report always says which one:"),
        bullet("A single reference doesn't match the candidate's claim -- for example, the reference says a different job title, or gives employment dates that are off by more than a small margin."),
        bullet("A reference's overall tone is concerning -- hesitation, vague praise, declining to say whether they'd rehire the candidate, or an outright stated concern."),
        bullet("Two or more references disagree with each other -- not with the candidate's resume, but with one another. This is checked separately and is often the most telling signal: a skip-level manager calling someone a top performer while their direct report describes a difficult experience to work with is exactly the kind of thing that's easy to miss when references are read one at a time."),
        body("If none of those apply, the report is marked clean and delivered without waiting on anyone. If any of them apply, the report is flagged with the specific reason spelled out, so the reviewer isn't starting from scratch -- they're confirming or overriding a specific, visible concern."),

        h1("Example"),
        body("A candidate applies for a Sales Director role, claiming they held that title from 2020 to 2023. Two references are checked:"),
        bullet("Their former VP describes them as a top performer who consistently beat quota -- a clean, positive reference on its own."),
        bullet("A direct report who reported to them describes a difficult manager who took credit for the team's work."),
        body("Neither reference individually raises a concern about the resume -- dates and title both check out. But the two references disagree sharply with each other on what this person is like to work for. That disagreement is exactly what gets surfaced to a reviewer, with both reference summaries shown side by side, rather than being missed because each reference looked fine in isolation."),

        h1("Benefits"),
        bullet("Speed -- a reference check that used to take a person several minutes of reading and comparing per reference happens automatically in the time it takes to make a couple of calls to an AI service, typically seconds."),
        bullet("Consistency -- every reference is checked against the same criteria, every time, regardless of who's doing the hiring that week or how busy they are."),
        bullet("Nothing skipped -- cross-checking multiple references against each other happens automatically, every time, instead of being the first thing to get skipped when someone's in a hurry."),
        bullet("A visible trail -- every discrepancy, red flag, and decision is recorded with the reasoning behind it, not just a pass/fail stamp."),
        bullet("One consistent process regardless of reference format -- open-text and structured-form references are handled by the same pipeline and show up in the same report."),

        h1("What This Is Not"),
        bullet("Not an auto-reject system. Nothing gets automatically disqualified -- the system's only two outcomes are \u201cclean, no concerns\u201d and \u201cflagged for a person to look at,\u201d never a rejection decision on its own."),
        bullet("Not a replacement for the hiring manager's judgment, or for whatever compliance process already governs adverse hiring decisions at your organization -- this tool changes how reference information gets gathered and summarized, not who makes the decision or what your legal/compliance obligations are around using it."),
        bullet("Not a substitute for legal or compliance review of your reference-checking process itself -- rules around background checks and adverse action vary by jurisdiction and role, and that review needs to happen independently of this tool."),

        h1("Questions This Naturally Raises"),
        h2("Does a person still make the final call?"),
        body("Yes. The system's output is a report and a recommendation to review or not review -- it does not make a hiring decision, and every flagged case is designed to be reviewed by a person before anything happens."),
        h2("What if a reference is lying or being evasive?"),
        body("The tool can flag hesitation, vagueness, or declining to answer directly as a red flag worth a person's attention -- it can't independently verify whether a reference is telling the truth, the same limitation a human reviewer reading the same transcript would have."),
        h2("What happens to the underlying transcripts and forms?"),
        body("They're used to produce the report and are not retained longer than your organization's own reference-check record-keeping process calls for -- retention and storage policy is a deployment decision for your team, not something built into the analysis itself."),

        h1("Next Steps"),
        body("The system is built and demonstrable today against sample data; the technical companion document describes what's needed to connect it to a real reference-checking workflow (data sources, review-queue integration, and the compliance/legal review noted above)."),
      ],
    },
  ],
});

Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(OUT, buf);
  console.log("written:", OUT);
});
