-- OpenG2P native default stages under clean keys; old policies/tasks remain intact.
INSERT INTO public.approval_stage (id,policy_id,stage_order,name,mode,mode_value,sla_hours,parallel_group,skip_if,on_empty,on_breach,escalation_rules_json,created_at,updated_at)
SELECT v.id,p.id,v.stage_order,v.name,'all',CAST(NULL AS integer),CAST(NULL AS integer),CAST(NULL AS integer),'null','block',CAST(NULL AS integer),'null',NOW(),NOW()
FROM (VALUES
('5016cdbc-e2e2-53e2-a45e-eafc1ae9ea87','registry.change_request.farmer.default',1,'Stage 1 Officers'),
('3a336a03-a850-5b67-8c56-9700e3c176f8','registry.change_request.farmer.default',2,'Stage 2 Officers'),
('f966fa24-f45f-5fa7-8366-a325fdaf06f3','registry.change_request.household.default',1,'Stage 1 Officers'),
('c14bd3e5-0b1b-522c-a17e-e9b4cdd6fe03','registry.change_request.household.default',2,'Stage 2 Officers'),
('89a739ce-e945-51a4-807c-9c38df6b338f','registry.intake_form.farmer.default',1,'Stage 1 Officers'),
('e6ce3511-e5c3-5b14-9be1-e62c5db2c32d','registry.intake_form.farmer.default',2,'Stage 2 Officers'),
('56c5efb3-f7cc-58d8-82a2-d17fba6e5ece','registry.intake_form.household.default',1,'Stage 1 Officers'),
('d94505a0-e0c4-5dab-8dd3-0073d6878059','registry.intake_form.household.default',2,'Stage 2 Officers')) AS v(id,policy_key,stage_order,name)
JOIN public.approval_policy p ON p.policy_key=v.policy_key AND p.version=1
WHERE NOT EXISTS (SELECT 1 FROM public.approval_stage s WHERE s.policy_id=p.id AND s.stage_order=v.stage_order)
ON CONFLICT (id) DO NOTHING;
