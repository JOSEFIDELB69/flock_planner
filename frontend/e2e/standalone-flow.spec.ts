import { expect, test } from "@playwright/test";

/**
 * Flujo autónomo completo por la interfaz (sin JIRA):
 * proyecto → requisitos → análisis → backlog → línea base → escenarios → aplicar → PDF.
 * Requiere el backend con AI_PROVIDER=demo (resultados simulados) o con Claude Code (sesión iniciada).
 */
test("flujo autónomo de punta a punta", async ({ page }) => {
  const name = `E2E Turnos ${Date.now()}`;

  await page.goto("/projects/new");
  await page.getByLabel("Nombre").fill(name);
  await page.getByLabel("Objetivo de negocio").fill("Reducir el ausentismo");
  await page.getByRole("button", { name: "Crear proyecto" }).click();
  await expect(page).toHaveURL(/\/projects\/\d+\/requirements$/);
  const projectUrl = page.url().replace(/\/requirements$/, "");

  // requisitos en texto libre
  await page.getByRole("button", { name: "Texto libre o archivo" }).click();
  await page.getByRole("dialog").locator("textarea").first().fill(
    "- El paciente reserva turnos desde una pantalla web.\n- El administrador gestiona agendas desde un panel.\n- El sistema envía recordatorios por email.",
  );
  await page.getByRole("button", { name: "Crear requisitos" }).click();
  await expect(page.getByText("REQ-003")).toBeVisible();

  // análisis con IA (o simulado en modo demostración)
  await page.getByRole("button", { name: "Analizar con IA" }).click();
  await expect(page.getByRole("heading", { name: "Análisis de requisitos" })).toBeVisible();
  await page.getByLabel(/Continuar con supuestos explícitos/).check();
  await page.getByRole("button", { name: "Guardar respuestas" }).click();
  await expect(page.getByText("Respuestas guardadas")).toBeVisible();

  // backlog
  await page.goto(`${projectUrl}/stories`);
  await page.getByRole("button", { name: "Generar backlog con IA" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Generar backlog" }).click();
  await expect(page.getByText(/^Backlog generado: \d+ historias/)).toBeVisible();
  await expect(page.getByText("US-003")).toBeVisible();

  // planificación: vista previa (no guardada) y línea base
  await page.goto(`${projectUrl}/planning`);
  await page.getByRole("button", { name: "Calcular vista previa" }).click();
  await expect(page.getByText("Vista previa: estimación preliminar, todavía no guardada")).toBeVisible();
  await page.getByRole("button", { name: "Confirmar como línea base" }).click();
  await page.getByRole("dialog").getByRole("button", { name: "Confirmar línea base" }).click();
  await expect(page.getByText("Línea base · inmutable")).toBeVisible();

  // optimización: escenarios sugeridos y aplicación
  await page.goto(`${projectUrl}/optimization`);
  await page.getByRole("button", { name: "Sugerir escenarios" }).first().click();
  await expect(page.getByRole("heading", { name: "Comparación de escenarios" })).toBeVisible();
  await expect(page.getByText("Recomendado")).toBeVisible();
  await page.getByRole("button", { name: /^Aplicar / }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Aplicar escenario" }).click();
  await expect(page.getByText(/Escenario aplicado: se creó la versión v2/)).toBeVisible();

  // versiones: la línea base sigue existiendo
  await page.goto(`${projectUrl}/versions`);
  await expect(page.getByRole("cell", { name: /v2/ }).first()).toBeVisible();
  await expect(page.getByText("Línea base", { exact: true }).first()).toBeVisible();

  // PDF real descargable
  await page.goto(`${projectUrl}/reports`);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("button", { name: "Generar y descargar PDF" }).first().click();
  const download = await downloadPromise;
  expect(download.suggestedFilename()).toMatch(/^Flock_Planner_.*_Plan_v2\.pdf$/);
  const stream = await download.createReadStream();
  const chunks: Buffer[] = [];
  for await (const c of stream) chunks.push(c as Buffer);
  const pdf = Buffer.concat(chunks);
  expect(pdf.subarray(0, 5).toString()).toBe("%PDF-");
  expect(pdf.length).toBeGreaterThan(5000);
});
