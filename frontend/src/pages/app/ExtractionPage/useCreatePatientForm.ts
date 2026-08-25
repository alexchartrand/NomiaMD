import { useState, type FormEvent } from "react";
import { createPatient, describeError, type Gender, type Patient, type PatientInput } from "../../../api";

export interface CreatePatientFormState {
  full_name: string;
  ramq_number: string;
  date_of_birth: string;
  gender: Gender | null;
}

const BLANK_FORM: CreatePatientFormState = {
  full_name: "",
  ramq_number: "",
  date_of_birth: "",
  gender: null,
};

interface UseCreatePatientFormOptions {
  onCreated: (patient: Patient) => void;
}

export function useCreatePatientForm({ onCreated }: UseCreatePatientFormOptions) {
  const [visible, setVisible] = useState(false);
  const [form, setForm] = useState<CreatePatientFormState>(BLANK_FORM);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  function open(initial: Partial<CreatePatientFormState>) {
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
        is_registered_with_physician: false,
        is_vulnerable: false,
      };
      // Does not re-run /extract — that would burn two more LLM calls and the 10/minute limit.
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
