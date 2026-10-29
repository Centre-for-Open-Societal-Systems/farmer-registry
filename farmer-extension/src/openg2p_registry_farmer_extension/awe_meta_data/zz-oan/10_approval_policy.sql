-- OpenG2P native default stages under clean keys; old policies/tasks remain intact.
INSERT INTO public.approval_policy (id,policy_key,version,name,description,status,artifact_type,created_by,forbid_self_approval,forbid_repeat_approvers,created_at,updated_at) VALUES
('840ad17e-75e9-5441-9f25-2e577cbf97e1','registry.change_request.farmer.default',1,'change_request.farmer - OpenG2P defaults',NULL,'active','registry.change_request','seed',FALSE,FALSE,NOW(),NOW()),
('77a5f20f-faf5-51df-b247-3532b2db399f','registry.change_request.household.default',1,'change_request.household - OpenG2P defaults',NULL,'active','registry.change_request','seed',FALSE,FALSE,NOW(),NOW()),
('54281fda-9fe5-5ea9-a550-ef6c104a19b7','registry.intake_form.farmer.default',1,'intake_form.farmer - OpenG2P defaults',NULL,'active','registry.intake_form','seed',FALSE,FALSE,NOW(),NOW()),
('aecf6e7b-c0ac-50c5-bb41-8e448b26a318','registry.intake_form.household.default',1,'intake_form.household - OpenG2P defaults',NULL,'active','registry.intake_form','seed',FALSE,FALSE,NOW(),NOW())
ON CONFLICT (policy_key,version) DO NOTHING;
