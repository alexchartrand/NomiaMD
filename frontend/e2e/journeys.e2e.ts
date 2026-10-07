import { expect, test, type Page } from "@playwright/test";
import { login } from "./helpers";

// Synthetic note with no NAM: the intake can't resolve a patient, so it waits "à associer".
const UNASSIGNED_NOTE = `**Clinique :** Clinique médicale Les Tilleuls
**Médecin :** Dr. Louis-Philippe Gagné, MD, médecine familiale
**Date/heure :** 10 février 2026, 14h30

### Motif de consultation
Toux sèche depuis cinq jours, sans fièvre.

### Évaluation
Examen pulmonaire normal. Rhinopharyngite virale probable. Conseils de soutien.
`;

async function openAllEncounters(page: Page) {
  await page.getByRole("navigation").getByRole("link", { name: "Rencontres" }).click();
  await page.getByRole("button", { name: "Tout", exact: true }).click();
}

// One database for the whole run, so the journeys run in order and build on each other.
test.describe.serial("journeys", () => {
  test("extract a seeded note, pick codes, save the claim", async ({ page }) => {
    await login(page);
    await openAllEncounters(page);

    // Names and NAMs are masked in the list ("Roch D."), and the notes are dated over the
    // last weeks, so narrow to the one patient.
    await page.getByRole("textbox", { name: "Patient" }).fill("Roch");
    const row = page.getByRole("row").filter({ hasText: "Roch D." });
    await expect(row.getByText("Reçu", { exact: true })).toBeVisible();
    await row.getByRole("button", { name: "Extraire" }).click();
    await expect(row.getByText("Prêt", { exact: true })).toBeVisible();

    await row.getByRole("button", { name: "Réviser" }).click();
    await expect(page).toHaveURL(/\/app\/inbox\/\d+/);

    const firstCode = page.getByRole("checkbox", { name: /^Facturer le code / }).first();
    await firstCode.check();
    await page.getByRole("button", { name: "Enregistrer la facturation" }).click();
    await expect(page.getByRole("button", { name: "Enregistrer la facturation" })).toBeDisabled();

    // The claim is saved against the encounter: it reopens with the code still selected.
    await page.reload();
    await expect(page.getByRole("checkbox", { name: /^Facturer le code / }).first()).toBeChecked();
    await expect(page.getByRole("button", { name: "Enregistrer les modifications" })).toBeDisabled();
  });

  test("paste a note, associate its patient, get codes", async ({ page }) => {
    await login(page);
    await page.getByRole("link", { name: "Ajouter des notes" }).click();
    await page.getByRole("tab", { name: "Coller" }).click();
    await page.getByLabel("Notes à ajouter").fill(UNASSIGNED_NOTE);
    await page.getByLabel("Lot (facultatif)").fill("e2e");
    await page.getByRole("button", { name: "Ajouter aux rencontres" }).click();

    await openAllEncounters(page);
    const row = page.getByRole("row").filter({ hasText: "À associer" });
    await expect(row).toHaveCount(1);
    await row.getByRole("button", { name: "Associer un patient" }).click();
    await page.getByPlaceholder("Nom ou NAM du patient...").fill("Desjardins");
    await page.getByRole("option", { name: /Desjardins/ }).click();
    await page.getByRole("button", { name: "Associer", exact: true }).click();
    await expect(page.getByRole("row").filter({ hasText: "À associer" })).toHaveCount(0);

    // Picking the patient queues the extraction: the pasted note, grouped under its batch
    // label, ends up ready for review.
    await page.getByRole("textbox", { name: "Patient" }).fill("Roch");
    // The batch is its own table body inside the day's card, under its label.
    const batch = page.locator("tbody").filter({ has: page.getByRole("heading", { name: "e2e" }) });
    await expect(batch.getByText("Prêt", { exact: true })).toBeVisible();
    await expect(batch.getByRole("button", { name: "Réviser" })).toBeVisible();
  });

  test("bill the saved claims and download the PDF", async ({ page }) => {
    await login(page);
    await page.getByRole("navigation").getByRole("link", { name: "Facturation" }).click();
    await page.getByRole("button", { name: "Créer une facture" }).click();

    // Every draft, over the period that covers them, comes ticked.
    const dialog = page.getByRole("dialog");
    await expect(dialog.getByRole("checkbox", { name: "Tout sélectionner" })).toBeChecked();
    await dialog.getByRole("button", { name: "Générer la facture" }).click();
    await expect(dialog).toBeHidden();

    // …and the page moved to the generated bills.
    await expect(page.getByRole("tab", { name: "Factures générées" })).toHaveAttribute("aria-selected", "true");
    const pdf = page.getByRole("link", { name: "Télécharger le PDF" }).first();
    await expect(pdf).toBeVisible();

    const response = await page.request.get((await pdf.getAttribute("href"))!);
    expect(response.ok()).toBe(true);
    expect(response.headers()["content-type"]).toContain("application/pdf");
    expect((await response.body()).subarray(0, 4).toString()).toBe("%PDF");
  });
});
