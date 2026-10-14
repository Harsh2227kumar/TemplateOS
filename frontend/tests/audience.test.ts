// Run with `npm test`. Template audience model (id-based organization / department scope).
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  EMPTY_AUDIENCE,
  allowedVisibilities,
  audienceFromTemplate,
  departmentChoices,
  toAccessPayload,
  validateAudience,
  withOrganization,
  withScopeDefaults,
  type AudienceValue,
} from "../src/lib/audience.ts";
import type { TemplateAccessOptions } from "../src/lib/api/types.ts";

const UNI = 1;
const OTHER = 2;
const CS = 10;
const ME = 11;
const LAW = 20;

function options(over: Partial<TemplateAccessOptions> = {}): TemplateAccessOptions {
  return {
    roles: [
      { value: "faculty", label: "Faculty" },
      { value: "student", label: "Student" },
    ],
    organizations: [
      { id: UNI, name: "State University" },
      { id: OTHER, name: "Other College" },
    ],
    departments: [
      { id: ME, organization_id: UNI, name: "Mechanical" },
      { id: CS, organization_id: UNI, name: "Computer Science" },
      { id: LAW, organization_id: OTHER, name: "Law" },
    ],
    can_publish: { organization: true, department: true },
    defaults: { organization_id: null, department_id: null },
    ...over,
  };
}

const audience = (over: Partial<AudienceValue>): AudienceValue => ({ ...EMPTY_AUDIENCE, ...over });

test("visibilities follow can_publish", () => {
  assert.deepEqual(allowedVisibilities(null), ["private", "public", "group"]);
  assert.deepEqual(allowedVisibilities(options()), [
    "private",
    "public",
    "organization",
    "department",
    "group",
  ]);
  assert.deepEqual(
    allowedVisibilities(options({ can_publish: { organization: false, department: true } })),
    ["private", "public", "department", "group"],
  );
});

test("department choices belong to the organization, sorted by name", () => {
  assert.deepEqual(departmentChoices(options(), UNI).map((d) => d.name), [
    "Computer Science",
    "Mechanical",
  ]);
  assert.deepEqual(departmentChoices(options(), null), []);
  assert.deepEqual(departmentChoices(null, UNI), []);
});

test("validation needs ids and a department of the chosen organization", () => {
  const opts = options();
  assert.ok(validateAudience(EMPTY_AUDIENCE, opts, "super_admin").visibility);
  assert.ok(
    validateAudience(audience({ visibility: "organization" }), opts, "super_admin")
      .scope_organization_id,
  );
  assert.deepEqual(
    validateAudience(audience({ visibility: "organization", scope_organization_id: UNI }), opts, "super_admin"),
    {},
  );
  assert.ok(
    validateAudience(
      audience({ visibility: "department", scope_organization_id: UNI }),
      opts,
      "super_admin",
    ).scope_department_id,
  );
  assert.ok(
    validateAudience(
      audience({ visibility: "department", scope_organization_id: UNI, scope_department_id: LAW }),
      opts,
      "super_admin",
    ).scope_department_id,
  );
  assert.deepEqual(
    validateAudience(
      audience({ visibility: "department", scope_organization_id: UNI, scope_department_id: CS }),
      opts,
      "super_admin",
    ),
    {},
  );
  const restricted = validateAudience(
    audience({ visibility: "public", role_mode: "selected" }),
    opts,
    "faculty",
  );
  assert.ok(restricted.allowed_roles);
  // Admins without membership get a hint that points at the administrator.
  assert.match(
    validateAudience(audience({ visibility: "department" }), opts, "department_admin")
      .scope_department_id ?? "",
    /administrator/,
  );
});

test("payload sends ids and clears what the visibility does not use", () => {
  assert.deepEqual(
    toAccessPayload(
      audience({
        visibility: "department",
        scope_organization_id: UNI,
        scope_department_id: CS,
        role_mode: "selected",
        allowed_roles: ["faculty"],
      }),
    ),
    {
      visibility: "department",
      scope_organization_id: UNI,
      scope_department_id: CS,
      allowed_roles: ["faculty"],
    },
  );
  assert.deepEqual(
    toAccessPayload(
      audience({ visibility: "organization", scope_organization_id: UNI, scope_department_id: CS }),
    ),
    { visibility: "organization", scope_organization_id: UNI, scope_department_id: null, allowed_roles: null },
  );
  assert.deepEqual(
    toAccessPayload(audience({ visibility: "private", scope_organization_id: UNI, role_mode: "selected", allowed_roles: ["faculty"] })),
    { visibility: "private", scope_organization_id: null, scope_department_id: null, allowed_roles: null },
  );
});

test("editor state from a template", () => {
  assert.deepEqual(
    audienceFromTemplate({
      visibility: "department",
      scope_organization_id: UNI,
      scope_department_id: CS,
      allowed_roles: ["student"],
    }),
    {
      visibility: "department",
      scope_organization_id: UNI,
      scope_department_id: CS,
      role_mode: "selected",
      allowed_roles: ["student"],
    },
  );
});

test("scope defaults: forced for scoped admins, prefilled otherwise", () => {
  const opts = options({ defaults: { organization_id: UNI, department_id: CS } });
  const forced = withScopeDefaults(
    audience({ visibility: "department", scope_organization_id: OTHER, scope_department_id: LAW }),
    opts,
    "department_admin",
  );
  assert.equal(forced.scope_organization_id, UNI);
  assert.equal(forced.scope_department_id, CS);

  const superAdmin = withScopeDefaults(
    audience({ visibility: "department", scope_organization_id: OTHER }),
    opts,
    "super_admin",
  );
  // Keeps the chosen organization; the default department (another org's) is dropped.
  assert.equal(superAdmin.scope_organization_id, OTHER);
  assert.equal(superAdmin.scope_department_id, null);

  const orgOnly = withScopeDefaults(
    audience({ visibility: "organization", scope_department_id: CS }),
    opts,
    "org_admin",
  );
  assert.equal(orgOnly.scope_organization_id, UNI);
  assert.equal(orgOnly.scope_department_id, null);

  const unscoped = audience({ visibility: "public" });
  assert.equal(withScopeDefaults(unscoped, opts, "org_admin"), unscoped);
});

test("changing the organization drops a foreign department", () => {
  const opts = options();
  const start = audience({ visibility: "department", scope_organization_id: UNI, scope_department_id: CS });
  assert.equal(withOrganization(start, OTHER, opts).scope_department_id, null);
  assert.equal(withOrganization(start, UNI, opts).scope_department_id, CS);
  assert.equal(withOrganization(start, null, opts).scope_organization_id, null);
});
