#!/usr/bin/env node
// Score leads against our ICP and print a ranked shortlist.
//
// Deterministic, explainable scoring — no LLM needed — so the same leads always
// rank the same way in a demo, and every score comes with its reasons.

import { getLeads } from "./fetch_leads.mjs"

function argValue(flag, fallback) {
  const i = process.argv.indexOf(flag)
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback
}

// Title seniority — first match wins, higher is more senior.
const SENIORITY = [
  [/\b(head|chief|c[eto]o|vp|vice.?president)\b/i, 40, "senior leadership"],
  [/\bdirector\b/i, 32, "director-level"],
  [/\b(manager|lead)\b/i, 24, "manager-level"],
  [/\b(senior|principal|staff)\b/i, 16, "senior IC"],
]
// Departments we sell into.
const TARGET_DEPTS = { Engineering: 25, Marketing: 22, Sales: 22, Support: 10 }

export function scoreLead(lead) {
  let score = 0
  const reasons = []

  for (const [re, pts, why] of SENIORITY) {
    if (re.test(lead.title)) { score += pts; reasons.push(why); break }
  }
  const deptPts = TARGET_DEPTS[lead.department] ?? 0
  if (deptPts) { score += deptPts; reasons.push(`${lead.department} team`) }
  if (lead.email?.includes("@")) { score += 15; reasons.push("email on file") }
  if (lead.phone) { score += 10; reasons.push("phone on file") }
  if (lead.company) { score += 10; reasons.push("named account") }

  return { ...lead, score: Math.min(100, score), reasons }
}

function pad(s, n) { return String(s ?? "").padEnd(n).slice(0, n) }

const top = Number(argValue("--top", "10"))
const { leads, source } = await getLeads(100)
const ranked = leads.map(scoreLead).sort((a, b) => b.score - a.score).slice(0, top)

console.error(`# Top ${ranked.length} of ${leads.length} leads (source: ${source})\n`)
console.log(`${pad("score", 6)}${pad("name", 24)}${pad("title", 30)}company`)
console.log("-".repeat(78))
for (const l of ranked) {
  console.log(`${pad(l.score, 6)}${pad(l.name, 24)}${pad(l.title, 30)}${l.company}`)
}
console.log("\nWhy the top 3 fit the ICP:")
for (const l of ranked.slice(0, 3)) {
  console.log(`- ${l.name} (${l.score}/100): ${l.reasons.join(", ")}`)
}
