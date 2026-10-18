import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";

import { setToken } from "../../lib/auth";
import { jsonResponse, renderRoute, stubFetch } from "../../test/utils";

afterEach(() => act(() => setToken(null)));

async function signIn(next: string) {
  stubFetch({
    "POST /api/v1/auth/login": () => jsonResponse({ access_token: "tok", token_type: "bearer", expires_in: 3600 }),
  });
  const { router } = renderRoute(`/login?next=${encodeURIComponent(next)}`);
  await userEvent.type(await screen.findByLabelText("Email"), "a@example.com");
  await userEvent.type(screen.getByLabelText("Password"), "correct-horse-battery");
  await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
  return router;
}

describe("sign-in redirect", () => {
  it("returns to the requested in-app page", async () => {
    const router = await signIn("/watchlists");
    await waitFor(() => expect(router.state.location.pathname).toBe("/watchlists"));
  });

  it.each(["//evil.example", "/\\evil.example", "https://evil.example"])("ignores unsafe next=%s", async (next) => {
    const router = await signIn(next);
    await waitFor(() => expect(router.state.location.pathname).toBe("/"));
  });
});
