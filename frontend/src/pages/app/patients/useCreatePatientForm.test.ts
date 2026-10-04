import { act, renderHook } from "@testing-library/react";
import type { FormEvent } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../../../test/server";
import type { Patient } from "../../../api";
import { useCreatePatientForm } from "./useCreatePatientForm";

const created: Patient = {
  id: 3,
  full_name: "Patient Test",
  ramq_number: "TEST12345678",
  date_of_birth: "1980-05-01",
  gender: null,
  is_vulnerable: false,
  family_doctor_name: null,
  family_doctor_practice_number: null,
  is_registered_with_current_physician: null,
};

const submitEvent = { preventDefault: vi.fn() } as unknown as FormEvent;

function setup() {
  const onCreated = vi.fn();
  const view = renderHook(() => useCreatePatientForm({ onCreated }));
  return { ...view, onCreated };
}

describe("useCreatePatientForm", () => {
  it("starts hidden and opens with the given prefill over a blank form", () => {
    const { result } = setup();
    expect(result.current.visible).toBe(false);
    act(() => result.current.open({ ramq_number: "TEST12345678" }));
    expect(result.current.visible).toBe(true);
    expect(result.current.form).toMatchObject({ ramq_number: "TEST12345678", full_name: "", is_vulnerable: false });
  });

  it("resets the form and error each time it opens", async () => {
    const { result } = setup();
    act(() => result.current.open());
    await act(() => result.current.submit(submitEvent));
    expect(result.current.error).not.toBeNull();
    act(() => result.current.update({ full_name: "X" }));
    act(() => result.current.close());
    act(() => result.current.open());
    expect(result.current.error).toBeNull();
    expect(result.current.form.full_name).toBe("");
  });

  it("requires a name and a date of birth, without calling the server", async () => {
    const posts = vi.fn();
    server.use(http.post("/api/patients", () => (posts(), HttpResponse.json(created))));
    const { result, onCreated } = setup();
    act(() => result.current.open());
    act(() => result.current.update({ full_name: "   " }));
    await act(() => result.current.submit(submitEvent));
    expect(result.current.error).toBe("Le nom et la date de naissance sont obligatoires.");
    act(() => result.current.update({ full_name: "Patient Test" }));
    await act(() => result.current.submit(submitEvent));
    expect(result.current.error).toBe("Le nom et la date de naissance sont obligatoires.");
    expect(posts).not.toHaveBeenCalled();
    expect(onCreated).not.toHaveBeenCalled();
  });

  it("posts trimmed values with blanks as null, then reports the patient and closes", async () => {
    let body: unknown;
    server.use(
      http.post("/api/patients", async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(created);
      }),
    );
    const { result, onCreated } = setup();
    act(() => result.current.open());
    act(() =>
      result.current.update({
        full_name: "  Patient Test ",
        ramq_number: " TEST12345678 ",
        date_of_birth: "1980-05-01",
        gender: "F",
        is_vulnerable: true,
        family_doctor_name: "   ",
      }),
    );
    await act(() => result.current.submit(submitEvent));
    expect(submitEvent.preventDefault).toHaveBeenCalled();
    expect(body).toEqual({
      full_name: "Patient Test",
      ramq_number: "TEST12345678",
      date_of_birth: "1980-05-01",
      gender: "F",
      is_vulnerable: true,
      family_doctor_name: null,
      family_doctor_practice_number: null,
    });
    expect(onCreated).toHaveBeenCalledWith(created);
    expect(result.current.visible).toBe(false);
    expect(result.current.submitting).toBe(false);
  });

  it("keeps the form open and shows the server's error", async () => {
    server.use(http.post("/api/patients", () => HttpResponse.json({ detail: "NAM déjà utilisé" }, { status: 409 })));
    const { result, onCreated } = setup();
    act(() => result.current.open({ full_name: "Patient Test", date_of_birth: "1980-05-01" }));
    await act(() => result.current.submit(submitEvent));
    expect(result.current.error).toBe("NAM déjà utilisé");
    expect(result.current.visible).toBe(true);
    expect(result.current.submitting).toBe(false);
    expect(onCreated).not.toHaveBeenCalled();
  });
});
