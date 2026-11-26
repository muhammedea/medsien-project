// Minimal CSV reading for the upload preview. The engine's loader is the real parser and judge.

export const EXPECTED_COLUMNS = ["t", "request_id", "work_units", "mem_mb"];

function splitLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let quoted = false;
  for (let i = 0; i < line.length; i++) {
    const c = line[i];
    if (quoted) {
      if (c === '"' && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else if (c === '"') quoted = false;
      else cur += c;
    } else if (c === '"') quoted = true;
    else if (c === ",") {
      out.push(cur);
      cur = "";
    } else cur += c;
  }
  out.push(cur);
  return out;
}

export type CsvPreview = {
  header: string[];
  rows: string[][]; // first `previewRows` data rows
  rowCount: number; // all non-blank data rows
  missingColumns: string[];
};

export function previewCsv(text: string, previewRows = 10): CsvPreview {
  const lines = text.replace(/^﻿/, "").split(/\r?\n/).filter((l) => l.trim() !== "");
  const header = lines.length ? splitLine(lines[0]).map((h) => h.trim()) : [];
  const data = lines.slice(1);
  return {
    header,
    rows: data.slice(0, previewRows).map(splitLine),
    rowCount: data.length,
    missingColumns: EXPECTED_COLUMNS.filter((c) => !header.includes(c)),
  };
}
