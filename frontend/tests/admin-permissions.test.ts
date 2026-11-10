// Run with `npm test`. Which roles / fields the user-management UI offers.
import { test } from "node:test";
import assert from "node:assert/strict";

import {
  USER_ROLES,
  assignableRoles,
  buildUserUpdate,
  canChangeActive,
  canChangeInstitute,
  canChangeMemberType,
  canChangePlacement,
  canCreateApprovers,
  canCreateUnder,
  canEditDirectoryRow,
  canEndApprover,
  canRunSync,
  canViewSync,
  eklinkAdminUrl,
  eklinkUserUrl,
  isEklinkManaged,
  canManageApprovers,
  canManageInstitutes,
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
  assert.equal(isUserAdmin("institute_admin"), true);
  for (const role of ["faculty", "staff", "student", "approver", "normal_user", "", undefined, null]) {
    assert.equal(isUserAdmin(role), false, String(role));
  }
});

test("which roles each admin may assign", () => {
  assert.deepEqual(assignableRoles("super_admin"), [...USER_ROLES]);
  assert.deepEqual(assignableRoles("org_admin"), [
    "institute_admin",
    "department_admin",
    "faculty",
    "staff",
    "student",
  ]);
  assert.deepEqual(assignableRoles("institute_admin"), [
    "department_admin",
    "faculty",
    "staff",
    "student",
  ]);
  assert.deepEqual(assignableRoles("department_admin"), ["faculty", "staff", "student"]);
  // Legacy roles are never offered.
  for (const role of ["super_admin", "org_admin", "institute_admin", "department_admin"]) {
    assert.ok(!assignableRoles(role).includes("approver"));
    assert.ok(!assignableRoles(role).includes("normal_user"));
  }
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
  // Legacy roles rank as members: a department admin may convert them.
  assert.equal(canEditUser(csAdmin, member(13, "normal_user", UNI, CS)), true);
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
  assert.equal(canChangeDepartment(member(30, "institute_admin", UNI)), true);
  assert.equal(canChangeInstitute(uniAdmin), true);
  assert.equal(canChangeInstitute(member(30, "institute_admin", UNI)), false);
});

test("institute admins see and manage their institute only", () => {
  const SIT = 100;
  const SIBM = 101;
  const sitAdmin: Member = { id: 40, role: "institute_admin", organization_id: UNI, institute_id: SIT, department_id: null };
  const sitFaculty: Member = { id: 41, role: "faculty", organization_id: UNI, institute_id: SIT, department_id: CS };
  const sibmFaculty: Member = { id: 42, role: "faculty", organization_id: UNI, institute_id: SIBM, department_id: ME };
  assert.equal(canSeeUser(sitAdmin, sitFaculty), true);
  assert.equal(canSeeUser(sitAdmin, sibmFaculty), false);
  assert.equal(canEditUser(sitAdmin, sitFaculty), true);
  assert.deepEqual(roleChoices(sitAdmin, sitFaculty), ["department_admin", "faculty", "staff", "student"]);
  assert.equal(canManageDepartments(sitAdmin, UNI, SIT), true);
  assert.equal(canManageDepartments(sitAdmin, UNI, SIBM), false);
  assert.equal(canManageInstitutes(sitAdmin, UNI), false);
  assert.equal(canManageInstitutes(uniAdmin, UNI), true);
  assert.equal(canManageApprovers("institute_admin"), true);
  assert.equal(canManageApprovers("faculty"), false);
});

test("nobody deactivates themselves", () => {
  assert.equal(canChangeActive(csAdmin, csAdmin), false);
  assert.equal(canChangeActive(csAdmin, csFaculty), true);
  assert.deepEqual(
    buildUserUpdate(csAdmin, { ...csFaculty, is_active: true }, {
      role: "faculty", organization_id: UNI, department_id: CS, is_active: false,
    }),
    { is_active: false },
  );
});

test("role choices include the current role and only assignable ones", () => {
  assert.deepEqual(roleChoices(csAdmin, csFaculty), ["faculty", "staff", "student"]);
  // A legacy role is shown as the current value but never offered to others.
  assert.deepEqual(roleChoices(csAdmin, member(13, "normal_user", UNI, CS)), ["normal_user", "faculty", "staff", "student"]);
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

// ── EkLink ownership (SYNC_CONTRACT.md section 7) ──

const linkedFaculty: Member = { ...member(30, "faculty", UNI, CS), member_type: "faculty", managed_by_eklink: true };
const linkedAdmin: Member = { ...member(31, "department_admin", UNI, CS), member_type: "faculty", managed_by_eklink: true };

test("EkLink-linked users: placement, member type and active flag are read-only", () => {
  assert.equal(isEklinkManaged(linkedFaculty), true);
  assert.equal(isEklinkManaged(csFaculty), false);
  assert.equal(isEklinkManaged(null), false);
  assert.equal(canChangePlacement(linkedFaculty), false);
  assert.equal(canChangePlacement(csFaculty), true);
  assert.equal(canChangeActive(superAdmin, linkedFaculty), false);
  assert.equal(canChangeActive(superAdmin, csFaculty), true);
  assert.equal(canChangeMemberType(superAdmin, linkedAdmin), false);
  assert.equal(canChangeMemberType(superAdmin, { ...linkedAdmin, managed_by_eklink: false }), true);
  // still editable (admin roles)
  assert.equal(canEditUser(superAdmin, linkedFaculty), true);
});

test("EkLink-linked users: only admin roles or their member type are offered", () => {
  assert.deepEqual(roleChoices(superAdmin, linkedFaculty), [
    "super_admin",
    "org_admin",
    "institute_admin",
    "department_admin",
    "faculty",
  ]);
  assert.deepEqual(roleChoices(csAdmin, linkedFaculty), ["faculty"]);
  assert.deepEqual(roleChoices(superAdmin, linkedAdmin).slice(-1), ["faculty"]);
});

test("EkLink-linked users: the update never carries EkLink-owned fields", () => {
  assert.deepEqual(
    buildUserUpdate(superAdmin, linkedFaculty, {
      role: "department_admin",
      organization_id: OTHER,
      institute_id: 99,
      department_id: LAW,
      member_type: "staff",
      is_active: false,
    }),
    { role: "department_admin" },
  );
  // a member role other than their EkLink member type is not sent
  assert.deepEqual(
    buildUserUpdate(superAdmin, linkedFaculty, { role: "student", organization_id: UNI, department_id: CS }),
    {},
  );
  // back to the member type is fine
  assert.deepEqual(
    buildUserUpdate(superAdmin, linkedAdmin, { role: "faculty", organization_id: UNI, department_id: CS }),
    { role: "faculty" },
  );
});

test("EkLink directory rows and approver jobs are read-only", () => {
  assert.equal(canEditDirectoryRow({ managed_by_eklink: true }), false);
  assert.equal(canEditDirectoryRow({ managed_by_eklink: false }), true);
  assert.equal(canEditDirectoryRow({}), true);
  assert.equal(canCreateUnder({ managed_by_eklink: true }), false);
  assert.equal(canCreateUnder(null), true);

  assert.equal(canCreateApprovers("org_admin", true), false);
  assert.equal(canCreateApprovers("org_admin", false), true);
  assert.equal(canCreateApprovers("faculty", false), false);
  assert.equal(canEndApprover("org_admin", { is_current: true, managed_by_eklink: true }), false);
  assert.equal(canEndApprover("org_admin", { is_current: true, managed_by_eklink: false }), true);
  assert.equal(canEndApprover("org_admin", { is_current: false }), false);
});

test("sync page permissions and EkLink links", () => {
  assert.equal(canViewSync("department_admin"), true);
  assert.equal(canViewSync("faculty"), false);
  assert.equal(canRunSync("super_admin"), true);
  assert.equal(canRunSync("org_admin"), false);
  assert.equal(
    eklinkUserUrl("http://localhost:3000/", "T 004"),
    "http://localhost:3000/admin/users?login_id=T%20004",
  );
  assert.equal(eklinkUserUrl("http://localhost:3000", null), "http://localhost:3000/admin/users");
  assert.equal(eklinkUserUrl(null, "T004"), null);
  assert.equal(eklinkAdminUrl("http://e.test", "directory"), "http://e.test/admin/directory");
});
