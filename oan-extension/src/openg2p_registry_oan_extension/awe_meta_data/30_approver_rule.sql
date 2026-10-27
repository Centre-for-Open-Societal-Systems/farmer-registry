-- OpenG2P native default stages under clean keys; old policies/tasks remain intact.
INSERT INTO public.approver_rule (id,stage_id,rule_type,rule_value,kind,required,created_at,updated_at)
SELECT v.id,s.id,'user',v.rule_value::json,'approver',FALSE,NOW(),NOW()
FROM (VALUES
('18996095-e906-53ef-9cb3-a416220063ae','registry.change_request.farmer.default',1,'{"user_id": "alex.carter"}'),
('5660c583-6ff9-521c-ae12-d072437ff444','registry.change_request.farmer.default',2,'{"user_id": "nina.patel"}'),
('01f818a7-1961-518e-8f15-dc28ea356180','registry.change_request.household.default',1,'{"user_id": "alex.carter"}'),
('863f9a7a-5e7f-51f8-b460-04137b0975b5','registry.change_request.household.default',2,'{"user_id": "nina.patel"}'),
('30fa0b18-e46e-5ab3-a574-987be893275d','registry.intake_form.farmer.default',1,'{"user_id": "alex.carter"}'),
('a9621de2-b393-5a97-a114-2ac64143fb17','registry.intake_form.farmer.default',2,'{"user_id": "nina.patel"}'),
('e3b06e13-591b-5ff7-8e66-e6bc946732f2','registry.intake_form.household.default',1,'{"user_id": "alex.carter"}'),
('f8d6485f-48c7-5bf7-9f64-61cb8a847a51','registry.intake_form.household.default',2,'{"user_id": "nina.patel"}')) AS v(id,policy_key,stage_order,rule_value)
JOIN public.approval_policy p ON p.policy_key=v.policy_key AND p.version=1
JOIN public.approval_stage s ON s.policy_id=p.id AND s.stage_order=v.stage_order
WHERE NOT EXISTS (SELECT 1 FROM public.approver_rule r WHERE r.stage_id=s.id AND r.rule_type='user' AND r.rule_value::text=v.rule_value)
ON CONFLICT (id) DO NOTHING;
