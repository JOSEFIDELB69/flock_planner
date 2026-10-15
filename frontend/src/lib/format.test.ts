import assert from "node:assert/strict";
import { test } from "node:test";

import { fmtDate, fmtNum, fmtPct, signedDays, slugKey, toggled, variationPct } from "./format.ts";

test("formato numérico argentino", () => {
  assert.equal(fmtNum(1234.5), "1.234,5");
  assert.equal(fmtNum(4552, 0), "4.552");
  assert.equal(fmtNum(null), "—");
});

test("fechas dd/mm/aaaa", () => {
  assert.equal(fmtDate("2026-10-26"), "26/10/2026");
  assert.equal(fmtDate(null), "—");
});

test("porcentajes con signo", () => {
  assert.equal(fmtPct(-37.5, 1, true), "−37,5 %");
  assert.equal(fmtPct(12, 0, true), "+12 %");
  assert.equal(fmtPct(0, 0, true), "±0 %");
});

test("variación del plazo coincide con la fórmula del backend", () => {
  // backend: round((s - b) / b * 100, 2)
  assert.equal(variationPct(16, 10), -37.5);
  assert.equal(variationPct(3, 2), -33.33);
  assert.equal(variationPct(0, 5), 0);
});

test("ahorro en días", () => {
  assert.equal(signedDays(6), "6 días menos");
  assert.equal(signedDays(-2), "2 días más");
  assert.equal(signedDays(0), "sin cambios");
});

test("toggled no muta el Set original (seguro ante doble ejecución en modo desarrollo)", () => {
  const original = new Set([1, 2]);
  const added = toggled(original, 3);
  const removed = toggled(original, 1);
  assert.deepEqual([...original], [1, 2]);
  assert.deepEqual([...added].sort(), [1, 2, 3]);
  assert.deepEqual([...removed], [2]);
  // aplicar la misma actualización dos veces sobre el mismo estado da el mismo resultado
  assert.deepEqual([...toggled(original, 3)].sort(), [...toggled(original, 3)].sort());
});

test("clave de perfil", () => {
  assert.equal(slugKey("Diseñador UX/UI"), "disenador_ux_ui");
});
