-- Databases seeded before this change hold these eight stages with mode 'all'
-- (the named officer alone). Set them in place to 'any-n' with one decision so
-- the named officer or admin completes the stage; stage and rule ids, policy
-- keys and bindings are unchanged, and the statement is a no-op once applied.
UPDATE public.approval_stage SET mode='any-n', mode_value=1, updated_at=NOW()
WHERE id IN (
    '5016cdbc-e2e2-53e2-a45e-eafc1ae9ea87',
    '3a336a03-a850-5b67-8c56-9700e3c176f8',
    'f966fa24-f45f-5fa7-8366-a325fdaf06f3',
    'c14bd3e5-0b1b-522c-a17e-e9b4cdd6fe03',
    '89a739ce-e945-51a4-807c-9c38df6b338f',
    'e6ce3511-e5c3-5b14-9be1-e62c5db2c32d',
    '56c5efb3-f7cc-58d8-82a2-d17fba6e5ece',
    'd94505a0-e0c4-5dab-8dd3-0073d6878059'
)
  AND (mode <> 'any-n' OR mode_value IS DISTINCT FROM 1);
