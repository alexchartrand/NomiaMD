import { useState, type FormEvent } from "react";
import { createPatient, describeError, type Gender, type Patient, type PatientInput } from "../../../api";

export interface CreatePatientFormState {
  full_name: string;
  ramq_number: string;
  date_of_birth: string;
  gender: Gender | null;
  is_vulnerable: boolean;
  family_doctor_name: string;
  family_doctor_practice_number: string;
}

const BLANK_FORM: CreatePatientFormState = {
  full_name: "",
  ramq_number: "",
  date_of_birth: "",
  gender: null,
  is_vulnerable: false,
  family_doctor_name: "",
  family_doctor_practice_number: "",
};

interface UseCreatePatientFormOptions {
  onCreated: (patient: Patient) => void;
}

// Shared between ExtractionPage/SourceStep.tsx (the "not found, create inline" escape
// hatch before extraction runs) and PatientsPage.tsx (the "brand new patient" flow) — a
// single global Patient identity is created either way, distinct from "add to my list"
// (see api/patients.ts's addToRoster).
export function useCreatePatientForm({ onCreated }: UseCreatePatientFormOptions) {
  const [visible, setVisible] = useState(false);
  const [form, setForm] = useState<CreatePatientFormState>(BLANK_FORM);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function open(initial: Partial<CreatePatientFormState> = {}) {
    setForm({ ...BLANK_FORM, ...initial });
    setError(null);
    setVisible(true);
  }

  function close() {
    setVisible(false);
  }

  function update(patch: Partial<CreatePatientFormState>) {
    setForm((prev) => ({ ...prev, ...patch }));
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError(null);
    if (!form.full_name.trim() || !form.date_of_birth) {
      setError("Le nom et la date de naissance sont obligatoires.");
      return;
    }
    setSubmitting(true);
    try {
      const payload: PatientInput = {
        full_name: form.full_name.trim(),
        ramq_number: form.ramq_number.trim() || null,
        date_of_birth: form.date_of_birth,
        gender: form.gender,
        is_vulnerable: form.is_vulnerable,
        family_doctor_name: form.family_doctor_name.trim() || null,
        family_doctor_practice_number: form.family_doctor_practice_number.trim() || null,
      };
      const created = await createPatient(payload);
      onCreated(created);
      setVisible(false);
    } catch (err) {
      setError(describeError(err));
    } finally {
      setSubmitting(false);
    }
  }

  return { visible, form, error, submitting, open, close, update, submit };
}
