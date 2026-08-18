#!/usr/bin/env node
// Pull leads from the CRM for the Lead Gen workspace.
//
// Primary source is a free, no-key mock API (DummyJSON) so this runs anywhere
// with zero setup. If the network is unavailable (hackathon wifi...), it falls
// back to the bundled scripts/seed-leads.json so a demo never fails.

import { readFile } from "node:fs/promises"
import { fileURLToPath } from "node:url"
import { dirname, join } from "node:path"

const API_BASE = process.env.LEADS_API_BASE ?? "https://dummyjson.com"
const here = dirname(fileURLToPath(import.meta.url))

function argValue(flag, fallback) {
  const i = process.argv.indexOf(flag)
  return i !== -1 && process.argv[i + 1] ? process.argv[i + 1] : fallback
}

/** Map a raw CRM record into the lead shape the rest of the workspace uses. */
function toLead(u) {
  return {
    id: u.id,
    name: `${u.firstName ?? ""} ${u.lastName ?? ""}`.trim(),
    email: u.email ?? "",
    phone: u.phone ?? "",
    title: u.company?.title ?? "",
    department: u.company?.department ?? "",
    company: u.company?.name ?? "",
    location: [u.address?.city, u.address?.state].filter(Boolean).join(", "),
  }
}

async function fetchLive(limit) {
  const url = `${API_BASE}/users?limit=${limit}&select=firstName,lastName,email,phone,company,address`
  const res = await fetch(url, { signal: AbortSignal.timeout(8000) })
  if (!res.ok) throw new Error(`CRM API returned ${res.status}`)
  const data = await res.json()
  return (data.users ?? []).map(toLead)
}

async function fetchSeed() {
  const raw = await readFile(join(here, "seed-leads.json"), "utf8")
  return JSON.parse(raw)
}

/** Leads plus where they came from, so callers can surface the source. */
export async function getLeads(limit = 30) {
  try {
    return { leads: await fetchLive(limit), source: "live:dummyjson" }
  } catch (err) {
    const seed = await fetchSeed()
    return { leads: seed.slice(0, limit), source: `offline-seed (${err.message})` }
  }
}

// Run directly → print the leads as JSON, with the source on stderr.
if (import.meta.url === `file://${process.argv[1]}`) {
  const limit = Number(argValue("--limit", "30"))
  const { leads, source } = await getLeads(limit)
  console.error(`# ${leads.length} leads from ${source}`)
  console.log(JSON.stringify(leads, null, 2))
}
