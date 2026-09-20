import { describe, expect, it } from "vitest";

import { queryKeys } from "./queryKeys";

describe("queryKeys", () => {
  it("uses one root and keeps resource parameters in the key", () => {
    expect(queryKeys.health()).toEqual(["mylabdata", "health"]);
    expect(queryKeys.molecules.list("MLD-1", 50, 100)).toEqual([
      "mylabdata",
      "molecules",
      "list",
      { query: "MLD-1", limit: 50, offset: 100 },
    ]);
  });
});
