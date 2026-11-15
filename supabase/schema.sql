-- Argos database. Built from contract/CONTRACT.md v0.2, sections 3, 4 and 6.
-- Applied to the Supabase project "Argos" by Hasan. Coding agents do not run this.
--
-- The rules this file enforces:
--   1. No anonymous access. The public key alone reads nothing.
--   2. A signed-in user reads only the device they are a member of.
--   3. Every read and write needs a session that passed its second factor (aal2).
--   4. Family never reads sensor readings. Clinicians never read the snapshot image
--      or join the live view.
--   5. The dashboard's only write is acknowledging an escalated incident.
--   6. The brain writes with the secret key, which stays on the laptop.

-- ---------------------------------------------------------------- tables

create table public.devices (
  id            uuid primary key,
  name          text not null,
  person_label  text not null,
  state         text not null default 'calm' check (state in ('calm', 'checking', 'alert')),
  last_seen_at  timestamptz,
  fw            text,
  caps          text[] not null default '{}'
);

create table public.members (
  user_id    uuid not null references auth.users (id) on delete cascade,
  device_id  uuid not null references public.devices (id) on delete cascade,
  role       text not null check (role in ('family', 'clinician')),
  label      text not null,
  primary key (user_id, device_id)
);

create table public.incidents (
  id               uuid primary key,
  device_id        uuid not null references public.devices (id) on delete cascade,
  trigger          text not null check (trigger in ('fall', 'help_call', 'stillness', 'manual')),
  status           text not null check (status in ('checking', 'stood_down', 'escalated', 'acknowledged')),
  confidence       real check (confidence between 0 and 1),
  started_at       timestamptz not null,
  ended_at         timestamptz,
  stood_down_by    text check (stood_down_by in ('voice', 'pat')),
  summary          text,
  snapshot_path    text,
  acknowledged_by  text,
  acknowledged_at  timestamptz,
  -- Privacy rule: nothing is stored about what Argos saw unless the check failed.
  constraint nothing_stored_unless_escalated check (
    (summary is null and snapshot_path is null) or status in ('escalated', 'acknowledged')
  )
);
create index incidents_device_started on public.incidents (device_id, started_at desc);

create table public.events (
  id           uuid primary key,
  device_id    uuid not null references public.devices (id) on delete cascade,
  incident_id  uuid references public.incidents (id) on delete cascade,
  at           timestamptz not null,
  kind         text not null,
  text         text not null,
  detail       jsonb not null default '{}'
);
create index events_device_at on public.events (device_id, at desc);
create index events_incident on public.events (incident_id);

create table public.readings (
  device_id       uuid not null references public.devices (id) on delete cascade,
  at              timestamptz not null,
  temp_c          real,
  tilt_deg        real,
  person_present  boolean not null,
  still_s         integer not null,
  primary key (device_id, at)
);

-- ---------------------------------------------------------------- grants
-- New tables are not exposed to the API unless granted. Grant the least that works.

revoke all on public.devices, public.members, public.incidents, public.events, public.readings
  from anon, authenticated;

grant select on public.devices, public.members, public.incidents, public.events, public.readings
  to authenticated;
grant update (status, acknowledged_by, acknowledged_at) on public.incidents to authenticated;

grant select, insert, update, delete
  on public.devices, public.members, public.incidents, public.events, public.readings
  to service_role;

-- ---------------------------------------------------------------- row level security

alter table public.devices   enable row level security;
alter table public.members   enable row level security;
alter table public.incidents enable row level security;
alter table public.events    enable row level security;
alter table public.readings  enable row level security;

-- Second factor, on everything. Restrictive: it narrows every other policy.
create policy "second factor required" on public.devices   as restrictive for all to authenticated
  using ((select auth.jwt() ->> 'aal') = 'aal2') with check ((select auth.jwt() ->> 'aal') = 'aal2');
create policy "second factor required" on public.members   as restrictive for all to authenticated
  using ((select auth.jwt() ->> 'aal') = 'aal2') with check ((select auth.jwt() ->> 'aal') = 'aal2');
create policy "second factor required" on public.incidents as restrictive for all to authenticated
  using ((select auth.jwt() ->> 'aal') = 'aal2') with check ((select auth.jwt() ->> 'aal') = 'aal2');
create policy "second factor required" on public.events    as restrictive for all to authenticated
  using ((select auth.jwt() ->> 'aal') = 'aal2') with check ((select auth.jwt() ->> 'aal') = 'aal2');
create policy "second factor required" on public.readings  as restrictive for all to authenticated
  using ((select auth.jwt() ->> 'aal') = 'aal2') with check ((select auth.jwt() ->> 'aal') = 'aal2');

create policy "members read their own membership" on public.members
  for select to authenticated
  using (user_id = (select auth.uid()));

create policy "members read their device" on public.devices
  for select to authenticated
  using (exists (select 1 from public.members m
                 where m.user_id = (select auth.uid()) and m.device_id = devices.id));

create policy "members read their device's incidents" on public.incidents
  for select to authenticated
  using (exists (select 1 from public.members m
                 where m.user_id = (select auth.uid()) and m.device_id = incidents.device_id));

create policy "members acknowledge an escalated incident" on public.incidents
  for update to authenticated
  using (status = 'escalated'
         and exists (select 1 from public.members m
                     where m.user_id = (select auth.uid()) and m.device_id = incidents.device_id))
  with check (status = 'acknowledged'
         and exists (select 1 from public.members m
                     where m.user_id = (select auth.uid()) and m.device_id = incidents.device_id));

create policy "members read their device's timeline" on public.events
  for select to authenticated
  using (exists (select 1 from public.members m
                 where m.user_id = (select auth.uid()) and m.device_id = events.device_id));

create policy "clinicians read sensor readings" on public.readings
  for select to authenticated
  using (exists (select 1 from public.members m
                 where m.user_id = (select auth.uid()) and m.device_id = readings.device_id
                   and m.role = 'clinician'));

-- ---------------------------------------------------------------- live updates

alter publication supabase_realtime
  add table public.devices, public.incidents, public.events, public.readings;

-- ---------------------------------------------------------------- the live view (contract section 6)
-- Frames are broadcast on the private topic view:<device id>. They are sent by the brain
-- over Realtime's own API and are never written to any table. Only family with a second
-- factor may listen. Nobody signed in may send.

create policy "family with second factor watch the live view" on realtime.messages
  for select to authenticated
  using (
    realtime.messages.extension = 'broadcast'
    and (select auth.jwt() ->> 'aal') = 'aal2'
    and exists (select 1 from public.members m
                where m.user_id = (select auth.uid())
                  and m.role = 'family'
                  and 'view:' || m.device_id::text = (select realtime.topic()))
  );

-- ---------------------------------------------------------------- the records channel
-- Public Realtime access is off, so the dashboard listens for record changes on a private
-- channel, and joining a private channel needs a policy that names its topic.
-- Topic: records:<device id>. Members with a second factor may join. Nobody may send.
-- What arrives on it is still decided by the row policies on each table.

create policy "members with second factor join their records channel" on realtime.messages
  for select to authenticated
  using (
    realtime.messages.extension = 'broadcast'
    and (select auth.jwt() ->> 'aal') = 'aal2'
    and exists (select 1 from public.members m
                where m.user_id = (select auth.uid())
                  and 'records:' || m.device_id::text = (select realtime.topic()))
  );

-- ---------------------------------------------------------------- snapshots
-- One still image per escalated incident, at incidents/<incident id>/snapshot.jpg in a
-- private bucket. Family with a second factor may read. The brain writes with the secret key.

insert into storage.buckets (id, name, public) values ('snapshots', 'snapshots', false)
  on conflict (id) do nothing;

create policy "family with second factor read snapshots" on storage.objects
  for select to authenticated
  using (
    bucket_id = 'snapshots'
    and (select auth.jwt() ->> 'aal') = 'aal2'
    and (storage.foldername(name))[1] = 'incidents'
    and exists (select 1 from public.incidents i
                join public.members m on m.device_id = i.device_id
                where m.user_id = (select auth.uid())
                  and m.role = 'family'
                  and i.id::text = (storage.foldername(name))[2])
  );

-- ---------------------------------------------------------------- the demo dog

insert into public.devices (id, name, person_label)
values ('a0000000-0000-4000-8000-000000000001', 'Argos', 'Eleni')
on conflict (id) do nothing;
