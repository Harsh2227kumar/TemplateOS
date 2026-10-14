// Run with `npm test`. Which roles / fields the user-management UI offers.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  USER_ROLES,
  assignableRoles,
  buildUserUpdate,
  canChangeDepartment,
  canChangeOrganization,
  canChangeRole,
  canEditUser,
  canManageDepartments,
  canManageOrganizations,
  canSeeUser,
  departmentsOf,
  isUserAdmin,
  roleChoices,
  validateUserEdit,
  type Member,
} from "../src/lib/admin-permissions.ts";

const UNI = 1;
const OTHER = 2;
const CS = 10;
const ME = 11;
const LAW = 20;

function member(id: number, role: string, org: number | null = UNI, dept: number | null = null): Member {
  return { id, role, organization_id: org, department_id: dept };
}

const superAdmin = member(1, "super_admin", null);
const uniAdmin = member(2, "org_admin", UNI);
const uniAdmin2 = member(3, "org_admin", UNI);
const csAdmin = member(4, "department_admin", UNI, CS);
const csFaculty = member(5, "faculty", UNI, CS);
const meFaculty = member(6, "faculty", UNI, ME);
const lawFaculty = member(7, "faculty", OTHER, LAW);
const newbie = member(8, "normal_user", null);

test("admin roles", () => {
  assert.equal(isUserAdmin("super_admin"), true);
  assert.equal(isUserAdmin("org_admin"), true);
  assert.equal(isUserAdmin("department_admin"), true);
  for (const role of ["faculty", "student", "approver", "normal_user", "", undefined, null]) {
    assert.equal(isUserAdmin(role), false, String(role));
  }
});

test("which roles each admin may assign", () => {
  assert.deepEqual(assignableRoles("super_admin"), [...USER_ROLES]);
  assert.deepEqual(assignableRoles("org_admin"), [
    "department_admin",
    "faculty",
    "student",
    "approver",
    "normal_user",
  ]);
  assert.deepEqual(assignableRoles("department_admin"), [
    "faculty",
    "student",
    "approver",
    "normal_user",
  ]);
  assert.deepEqual(assignableRoles("faculty"), []);
  assert.deepEqual(assignableRoles(undefined), []);
  // Never escalate past yourself.
  assert.ok(!assignableRoles("org_admin").includes("org_admin"));
  assert.ok(!assignableRoles("org_admin").includes("super_admin"));
  assert.ok(!assignableRoles("department_admin").includes("department_admin"));
});

test("visibility scope matches GET /admin/users", () => {
  assert.equal(canSeeUser(superAdmin, lawFaculty), true);
  assert.equal(canSeeUser(uniAdmin, meFaculty), true);
  assert.equal(canSeeUser(uniAdmin, lawFaculty), false);
  assert.equal(canSeeUser(uniAdmin, newbie), false);
  assert.equal(canSeeUser(csAdmin, csFaculty), true);
  assert.equal(canSeeUser(csAdmin, meFaculty), false);
  assert.equal(canSeeUser(csFaculty, csFaculty), false);
  // An org admin without an organization sees nobody else.
  assert.equal(canSeeUser(member(9, "org_admin", null), newbie), false);
});

test("who may be edited", () => {
  assert.equal(canEditUser(superAdmin, uniAdmin), true);
  assert.equal(canEditUser(uniAdmin, csAdmin), true);
  assert.equal(canEditUser(uniAdmin, uniAdmin2), false, "peers are off limits");
  assert.equal(canEditUser(uniAdmin, superAdmin), false);
  assert.equal(canEditUser(uniAdmin, lawFaculty), false, "other organization");
  assert.equal(canEditUser(csAdmin, csFaculty), true);
  assert.equal(canEditUser(csAdmin, member(12, "department_admin", UNI, CS)), false);
  assert.equal(canEditUser(csAdmin, meFaculty), false, "other department");
  assert.equal(canEditUser(csFaculty, csFaculty), false, "non-admins edit nobody");
  // Admins may open their own record (membership only).
  assert.equal(canEditUser(uniAdmin, uniAdmin), true);
});

test("nobody changes their own role", () => {
  for (const actor of [superAdmin, uniAdmin, csAdmin]) {
    assert.equal(canChangeRole(actor, actor), false, actor.role);
  }
  assert.equal(canChangeRole(superAdmin, uniAdmin), true);
  assert.equal(canChangeRole(csAdmin, csFaculty), true);
});

test("membership fields per actor", () => {
  assert.equal(canChangeOrganization(superAdmin), true);
  assert.equal(canChangeOrganization(uniAdmin), false);
  assert.equal(canChangeOrganization(csAdmin), false);
  assert.equal(canChangeDepartment(superAdmin), true);
  assert.equal(canChangeDepartment(uniAdmin), true);
  assert.equal(canChangeDepartment(csAdmin), false);
});

test("role choices include the current role and only assignable ones", () => {
  assert.deepEqual(roleChoices(csAdmin, csFaculty), ["faculty", "student", "approver", "normal_user"]);
  // Own record: the role is shown but cannot change.
  assert.deepEqual(roleChoices(uniAdmin, uniAdmin), ["org_admin"]);
  assert.deepEqual(roleChoices(superAdmin, uniAdmin), [...USER_ROLES]);
});

test("directory management", () => {
  assert.equal(canManageOrganizations("super_admin"), true);
  assert.equal(canManageOrganizations("org_admin"), false);
  assert.equal(canManageDepartments(superAdmin, OTHER), true);
  assert.equal(canManageDepartments(uniAdmin, UNI), true);
  assert.equal(canManageDepartments(uniAdmin, OTHER), false);
  assert.equal(canManageDepartments(csAdmin, UNI), false);
  assert.equal(canManageDepartments(member(9, "org_admin", null), null), false);
});

test("departments are filtered by organization", () => {
  const departments = [
    { id: CS, organization_id: UNI, name: "CS" },
    { id: ME, organization_id: UNI, name: "ME" },
    { id: LAW, organization_id: OTHER, name: "Law" },
  ];
  assert.deepEqual(departmentsOf(departments, UNI).map((d) => d.id), [CS, ME]);
  assert.deepEqual(departmentsOf(departments, OTHER).map((d) => d.id), [LAW]);
  assert.deepEqual(departmentsOf(departments, null), []);
});

test("edit validation", () => {
  const departmentOrg = new Map([
    [CS, UNI],
    [ME, UNI],
    [LAW, OTHER],
  ]);
  assert.deepEqual(
    validateUserEdit({ role: "faculty", organization_id: UNI, department_id: CS }, departmentOrg),
    {},
  );
  assert.ok(
    validateUserEdit({ role: "faculty", organization_id: UNI, department_id: LAW }, departmentOrg)
      .department_id,
  );
  assert.ok(
    validateUserEdit({ role: "org_admin", organization_id: null, department_id: null }, departmentOrg)
      .organization_id,
  );
  assert.ok(
    validateUserEdit(
      { role: "department_admin", organization_id: UNI, department_id: null },
      departmentOrg,
    ).department_id,
  );
});

test("update body holds only changed, permitted fields", () => {
  assert.deepEqual(
    buildUserUpdate(superAdmin, csFaculty, { role: "student", organization_id: OTHER, department_id: LAW }),
    { role: "student", organization_id: OTHER, department_id: LAW },
  );
  assert.deepEqual(
    buildUserUpdate(superAdmin, csFaculty, { role: "faculty", organization_id: UNI, department_id: CS }),
    {},
  );
  // org_admin: department yes, organization never.
  assert.deepEqual(
    buildUserUpdate(uniAdmin, csFaculty, { role: "faculty", organization_id: OTHER, department_id: ME }),
    { department_id: ME },
  );
  // department_admin: role only.
  assert.deepEqual(
    buildUserUpdate(csAdmin, csFaculty, { role: "student", organization_id: UNI, department_id: ME }),
    { role: "student" },
  );
  // Own role never sent.
  assert.deepEqual(
    buildUserUpdate(uniAdmin, uniAdmin, { role: "super_admin", organization_id: UNI, department_id: null }),
    {},
  );
  // Clearing a department is an explicit null.
  assert.deepEqual(
    buildUserUpdate(uniAdmin, csFaculty, { role: "faculty", organization_id: UNI, department_id: null }),
    { department_id: null },
  );
});
