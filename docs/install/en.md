# Climate Director — Installation Guide (English)

[![Buy me a coffee on Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)

This guide explains step by step how to install and configure Climate
Director. Simply follow the steps from top to bottom; each step builds on the
one before it.

## Contents

- [What is Climate Director](#what-is-climate-director)
- [What you need](#what-you-need)
- [Step 1 — Installing](#step-1--installing)
- [Step 2 — Adding the integration](#step-2--adding-the-integration)
- [The main menu](#the-main-menu)
- [Step 3 — General settings](#step-3--general-settings)
- [Step 4 — Zones](#step-4--zones)
- [Step 5 — Sources](#step-5--sources)
- [Step 6 — Air conditioning circuits](#step-6--air-conditioning-circuits)
- [Step 7 — Shared heat sources](#step-7--shared-heat-sources)
- [Step 8 — Exclusive groups](#step-8--exclusive-groups)
- [Step 9 — Quiet windows](#step-9--quiet-windows)
- [Step 10 — Residents](#step-10--residents)
- [Step 11 — Doors and windows](#step-11--doors-and-windows)
- [Step 12 — Save and close](#step-12--save-and-close)
- [What you get in Home Assistant](#what-you-get-in-home-assistant)
- [The switches and buttons](#the-switches-and-buttons)
- [Actions](#actions)
- [Pre-conditioning](#pre-conditioning)
- [Taking charge yourself](#taking-charge-yourself)
- [Judging a shadow run](#judging-a-shadow-run)
- [Blueprints and notifications](#blueprints-and-notifications)
- [Troubleshooting](#troubleshooting)
- [Languages](#languages)

## What is Climate Director

Climate Director is a Home Assistant integration that steers existing climate
appliances. It owns no hardware itself: it conducts the `climate` entities you
already have — a gas boiler, a heat pump, air conditioners. At every moment it
computes one coherent end state for the whole house and turns that into service
calls.

**Shadow mode is on by default.** The integration then computes every decision
and shows what it would have done, but steers nothing. That lets you run it
alongside your existing automations for weeks, and switch over only once you
trust it.

Three concepts form the foundation:

| Concept | Meaning |
|---|---|
| **Zone** | A room. Describes *what you want*: target temperature, when heating or cooling may start, and in which season. |
| **Source** | An appliance able to serve a zone, with a duty (heating, cooling or both), a preference order and an outdoor-temperature window. |
| **Air conditioning circuit** | One outdoor unit and the indoor units on it. Describes *what is technically possible at once*. |

The rule of thumb for a shared outdoor unit: all indoor units on one circuit
carry the same duty — heating, cooling, off, or fan-only. Two indoor units on
one outdoor unit therefore cannot have one heating while the other cools.
Climate Director knows which units belong together and resolves that conflict
for you.

## What you need

| Entity | Required | What for |
|---|---|---|
| One `climate.*` per zone | **yes** | without an appliance there is nothing to steer |
| One temperature sensor per zone | **yes** | without a reading the integration cannot tell too cold from too warm; a `climate.*` with `current_temperature` will do |
| `sensor.*` or `weather.*` outdoor temperature | no | only needed to set limits on outdoor temperature — gas below 3 °C, heat pump above it, say |
| `weather.*` or `sensor.*` precipitation | no | only when precipitation may lift the open-a-window bound |
| `person.*` or `device_tracker.*` per resident | yes, once you configure residents | otherwise that resident can never be home |
| A sleep sensor per resident | no | without one nobody ever counts as asleep |
| `binary_sensor.*` presence per zone | only when a zone runs on *the room itself* | then it is the only gate the zone has |
| `binary_sensor.*` door or window | no | suspends the attached zones while it is open |
| `calendar.*` | no | switches the holiday schedule on by itself; works only with a keyword |
| A season entity | no | only if you do not want the season derived from the month |

You need to create no helpers for any of this. The integration makes all its
switches and controls itself.

**Units:** the integration assumes a Home Assistant running in the metric system:
all temperatures are degrees Celsius and are not converted.

## Step 1 — Installing

**Minimum version:** Home Assistant **2025.3** or newer. The integration adds
its entities through `AddConfigEntryEntitiesCallback`, an API available since
2025.3.

**Through HACS** (recommended):

1. Open HACS.
2. Go to the three dots in the top right and choose **Custom repositories**.
3. Add this URL, with category **Integration**:

   ```
   https://github.com/Sarnog/ha-climate-director
   ```

4. Search HACS for **Climate Director**, install it, and restart Home Assistant.

**Manually:**

1. Download or clone this repository.
2. Copy the `custom_components/climate_director` folder into the
   `custom_components` folder of your Home Assistant configuration.
3. Restart Home Assistant.

## Step 2 — Adding the integration

1. Go to **Settings → Devices & services → Add integration**.
2. Find **Climate Director** and pick it.
3. Give the installation a **name**. That name becomes the title and precedes
   the name of every entity the integration creates.
4. Leave **Shadow mode** on. That way you watch along first before anything is
   actually steered.
5. Save. The installation appears on the **Integrations** tab.

Everything after that is built up under **Configure** on this integration.

## The main menu

Under **Configure** you find the main menu, in this order:

| Menu | What for |
|---|---|
| **General settings** | outdoor temperature, season, gates, windows, calendars, shadow mode |
| **Zones and sources** | per room: temperature, switch-on and switch-off points, and the appliances belonging to it |
| **Air conditioning circuits** | which indoor units share one outdoor unit |
| **Shared heat sources** | a boiler or heat pump several rooms draw on |
| **Exclusive groups** | appliances that may never run together |
| **Quiet windows** | hours in which the director starts nothing of its own accord |
| **Residents** | who is home, who is asleep, and everyone's schedule |
| **Doors and windows** | which openings silence which zones |
| **✅ Save and close** | only here is everything actually stored |

Two things make the menu pleasant:

- Every screen ends in **When you are done here**, with the choice *Keep these
  changes and go back* or *Discard and go back*.
- Every picker carries a **← Back to the main menu** row.

So nothing traps you. Going back always works, even with a half-filled screen —
what you typed is then thrown away. And **nothing** is stored until you pick
**Save and close** in the main menu.

## Step 3 — General settings

| Setting | What it does |
|---|---|
| **Outdoor temperature sensor** | feeds every outdoor limit. Without a sensor every limit counts as not met and the installation stands still |
| **Outdoor dead band** | how many degrees a running duty may carry on past its outdoor bound before it changes over; 0.5 by default, zero switches it off |
| **Heating system** | *Central* or *Per zone*, see below |
| **Season source** | where the season comes from: the month, an entity, or pinned to summer/winter |
| **Season entity** | only needed when the source is set to *entity*; the built-in `season.*` entity can be picked too |
| **Hemisphere** | which months count as summer when the season comes from the month: northern April–September, southern October–March |
| **Season choice** | the `select.*` entity *Season* sets the season by hand to Automatic, Summer or Winter; the choice survives a restart |
| **Somebody home must be awake** | on = the house waits for somebody home *and* awake; off = sleep does not count |
| **A resident's schedule must be open** | on = the house waits for the first schedule window; off = presence alone decides |
| **Holiday calendars** | which calendars may announce a holiday; several allowed |
| **Word that marks a holiday** | the keyword an event must carry; empty = calendars are ignored |
| **Pre-conditioning duration** | the ceiling on a single request; default 120 minutes |
| **Guest mode from / until** | the window in which guest mode applies; both empty = all day |
| **Report a zone stuck after** | after how many minutes of waiting a zone counts as stuck; 0 switches the sensor off |
| **Precipitation source** | a `weather.*` or `sensor.*` entity that says whether precipitation falls; empty = the precipitation rule does not take part |
| **States that count as precipitation** | which states of that entity mean precipitation; rain, snow and hail by default |
| **How long precipitation keeps counting (minutes)** | grace period after the precipitation stops; 15 minutes by default |
| **Shadow mode** | on = compute everything, steer nothing |

### Precipitation sets the outdoor bound aside

A zone's outdoor bound is a thrift rule with an assumption under it: if it is
nicer outside than in, you are better off opening a window than switching the
air conditioner on. When precipitation falls that window stays shut, so
nothing happens, while the room stays too warm or too cold.

Set a **precipitation source** to fix that. For as long as it reports
precipitation, Climate Director skips the **per-zone outdoor bound** — exactly
as a pre-conditioning request does. The dead band, the season and the
**per-source** outdoor bound keep applying; those still pick the appliance. The
grace period sees to it that a five-minute shower does not make the regulation
bounce. Without a source the precipitation rule does not take part.

A room without windows gains nothing from it. There, switch the zone's
**Precipitation does not lift the open-a-window rule** on, and the outdoor
bound keeps applying even while precipitation falls.

### Heating system: central or per zone

| Choice | What it means | How you fill it in |
|---|---|---|
| **Central** | One heat source for the whole house. Switching on for one room warms the rest along with it. Think of a single smart thermostat, with or without radiator knobs. | Put the **same** thermostat as a source under every zone |
| **Per zone** | Each part of the house can get its heat separately, through a zone valve or a heat source of its own. | Give each zone its **own** valve or appliance as a source; if there is one shared boiler, add it as a shared heat source |

Smart radiator knobs alone are not zoning: the house still has one circuit and
one heat source that switches on or off for everyone at once. Choose **Central**
then. One boiler with three zone valves is **Per zone**.

This setting changes nothing about who may run. It records what your
installation is, so the configuration check can warn you when your setup does
not match.

## Step 4 — Zones

A zone is a room. Per zone you set:

| Setting | What it does |
|---|---|
| **Name** | the label that appears everywhere |
| **Indoor temperature sensor** | what the dead band works from; a `climate.*` measuring itself will do |
| **Precedence on a shared outdoor unit** | how strongly this zone claims a shared outdoor unit; **lower wins**. On one circuit no number may appear twice |
| **What decides whether this zone runs** | *the household* (schedule, sleep, somebody home) or *the room itself* (only the presence sensor) |
| **Presence sensor + state + grace period** | when the room counts as occupied; the grace period absorbs flickering detectors |
| **Precipitation does not lift the open-a-window rule** | on for a room without windows; there the outdoor bound keeps applying even while precipitation falls |
| **This zone may heat** | off = this room is never heated |
| **Target temperature for heating** | the setpoint handed to the appliance once heating runs — not the start point |
| **Start heating at** | heating starts at this indoor temperature or below |
| **Heating dead band** | how far above the start point heating stops |
| **Only heat below this outdoor temperature** | above it heating stays off; empty = no limit |
| **This zone may cool** | off = this room is never cooled |
| **Target temperature for cooling** | the setpoint handed to the appliance once cooling runs |
| **Start cooling at** | cooling starts at this indoor temperature or above |
| **Cooling dead band** | how far below the start point cooling stops |
| **Only cool above this outdoor temperature** | below it cooling stays off; empty = no limit |
| **Only cool in summer** | ties cooling to the season from the general settings |

### How the dead band works

Switching on and off happen at two different temperatures, so an appliance
cannot chatter on a tenth of a degree:

- heating starts at `indoor ≤ start point` and stops at `indoor ≥ start point + band`;
- cooling starts at `indoor ≥ start point` and stops at `indoor ≤ start point − band`.

The start point counts as reached, the stop point as passed. One degree of band
is a sensible start.

### What the screen refuses

Three combinations are refused on saving, because they produce a zone that is
there but never does anything:

- a **target on the wrong side of the start point** — the appliance is then set
  to a temperature it need do nothing for;
- **cooling that starts at or below where heating starts** — the two then ask
  for the same room at once;
- the zone set to **the room itself without a presence sensor**, or a zone that
  **may neither heat nor cool**.

### Household or the room itself

- **The household** (default): schedule, sleep and somebody-home all count. Set
  a presence sensor as well and it acts as an extra condition: the household
  must allow it **and** the room must be occupied.
- **The room itself**: schedule, sleep and somebody-home are skipped. Only the
  presence sensor decides. This requires a presence sensor, or the zone can
  never run.

That way one room can run on the schedule and another on presence.

## Step 5 — Sources

A source is an appliance able to serve the zone. Once you have saved a zone,
you pick its sources straight away.

| Setting | What it does |
|---|---|
| **Climate entity** | the appliance itself |
| **What this appliance can do** | heating only, cooling only, or both. A boiler is *heating only* |
| **Start this appliance automatically** | off leaves it alone, see below |
| **Order within this zone** | which source is preferred; **lower wins** |
| **Use from this outdoor temperature** | the lower bound; included in the range |
| **Use up to this outdoor temperature** | the upper bound; excluded from the range |

### Outdoor bounds: half open

The lower bound belongs to the window, the upper one does not. Two adjacent
sources thereby cover the whole scale, with no gap and no overlap.

Want gas below 3 °C and the air conditioner above it? Then do **not** put the
boundary at 3.0:

| Boundary | 2.9 °C | 3.0 °C | 3.1 °C |
|---|---|---|---|
| both at `3.0` | gas | **air conditioner** | air conditioner |
| both at `3.1` | gas | **gas** | air conditioner |

Set the boundary the same on **every** source, and never differently —
otherwise an overlap appears in which both are allowed.

### An appliance you switch on yourself

Turn **Start this appliance automatically** off for an appliance you operate by
hand (an air conditioner in a bedroom without a presence sensor, say). The
director:

- **never switches it on**, however cold or warm that room gets;
- **leaves it as you set it**;
- **switches it off only** when it runs a duty the shared outdoor unit cannot
  allow.

If a duty can only be done by such an appliance, the integration reports that
once under *Repairs*. Confirm the notice and it stays away — across restarts
too. If the zone later gains a new hand-operated duty, one fresh notice
follows.

If a duty can only be done by such an appliance, the integration reports that
once under *Repairs*. Confirm the notice and it stays away — across restarts
too. If the zone later gains a new hand-operated duty, one fresh notice
follows.

## Step 6 — Air conditioning circuits

Only needed when indoor units share an outdoor unit. If every unit has its own,
leave this empty.

| Setting | What it does |
|---|---|
| **Name** | a label to tell circuits apart |
| **Indoor units** | which `climate.*` entities hang on this outdoor unit. Include units the director does not manage: they claim the compressor too |
| **Can heat and cool at the same time** | off for an ordinary multi-split; on for a single split or three-pipe VRF with heat recovery |
| **Conflict policy** | who wins when two rooms want opposing duties |
| **A zone that loses may circulate air** | on = the loser goes to `fan_only` instead of off, but only when the unit knows that mode; otherwise it goes off |
| **Pause when swapping duty** | how long everything is off before the changeover |
| **Minimum run before swapping duty** | how long a duty must have run before the other may take over |
| **Rest before a unit may restart** | only ever delays starting, never stopping; default 180 seconds |
| **Maximum units running at once** | the capacity limit of the outdoor unit; empty = no cap |

### Conflict policies

| Policy | Behaviour |
|---|---|
| **Priority** (default) | the zone with the lowest priority number wins |
| **First come** | the duty already running keeps the circuit; a new request waits |
| **Demand** | the largest deviation from the setpoint wins |
| **Season** | the season dictates the duty; anything opposing it stands down |

## Step 7 — Shared heat sources

A boiler or heat pump several rooms draw on through their own valves. Leave
this empty when the system fires its own burner as soon as a valve asks.

| Setting | What it does |
|---|---|
| **Name** | a label to tell heat sources apart |
| **Climate entity** | the boiler or heat pump itself; must not also be a zone's source, or it would receive two commands |
| **Zones it serves** | empty = every room |
| **Fixed target temperature** | empty = it follows the warmest target among the rooms asking |

The heat source runs while any room it serves is being heated, and stops once
none is.

## Step 8 — Exclusive groups

Want two appliances to run **never** at the same time — a gas boiler and a heat
pump, say? Do not entrust that to the outdoor bounds alone. One value left
behind is enough to have them fire together. Put them in an exclusive group
instead: of the appliances in one group only one ever runs.

Mind what a group means: **one** appliance from the group at a time. If you want
the gas boiler to stay out of every air conditioner's way, while two air
conditioners on the same circuit may still cool together, make one group per
pair — gas with the one, gas with the other.

A group is about the **appliance**, not about the room. If the same boiler
sits under three rooms you only have to tick it once - wherever you pick it
from, it counts everywhere. And two rooms asking for that same boiler are not in
each other's way: that is one appliance running.

A group also binds appliances you switch on yourself: when another member of the
group gets its turn, the hand-operated appliance goes off. And the other way
round: when such an appliance is already running it occupies the group, and
another member waits.

## Step 9 — Quiet windows

Hours in which the director **starts nothing of its own accord**. Coming home at
eleven at night when you are about to turn in need not fire the boiler.

It is a brake on **starting**, not on continuing:

- whatever already runs stays regulated;
- switch something on yourself and it is picked up;
- whatever is off stays off until the window has passed.

Windows may cross midnight and carry weekdays. A household turning in at nine on
weekdays and at eleven at weekends sets two:

| From | Until | Days |
|---|---|---|
| 21:00 | 09:00 | Mon Tue Wed Thu Sun |
| 23:00 | 09:00 | Fri Sat |

Set no windows and the brake does not apply.

## Step 10 — Residents

Leave this empty for a building where nobody is tracked; the presence gates are
then skipped instead of blocking everything forever.

| Setting | What it does |
|---|---|
| **Name** | a label to tell residents apart |
| **Presence sensor** | usually a `person.*`; says whether this resident is home |
| **Sleep sensor** | when this resident is asleep; empty = sleep is not tracked |
| **State meaning asleep** | the state the sleep sensor reports when asleep |
| **Sleep sensor counts from / until** | the hours in which that sensor means anything; both empty = around the clock |
| **Sleep window days** | the days that window applies on; empty = every day |

### Schedules

Once you have saved a resident, you set their schedules:

| Setting | What it does |
|---|---|
| **This is a holiday window** | applies only during the holiday schedule, replacing the ordinary windows then |
| **From / Until** | the window; may cross midnight |
| **Days** | empty = every day |

A resident without a schedule does not take part in the schedule gate. Somebody
with no window on a day does not hold the house back that day.

### Sleep sensor: no sensor, but a button?

A button (`button` or `input_button`) cannot say whether you are asleep — its
state is the moment of the last press. What does work is an `input_boolean` you
toggle with a button: create the toggle, pick it as the sleep sensor with `on`
as the sleeping state, and let a button switch it. Anyone who does have a sleep
sensor (a bed sensor, a wireless charger) uses that: it is more accurate.

Leave the sleep sensor empty and that resident never counts as asleep.

## Step 11 — Doors and windows

An opening standing open long enough suspends the zones it affects.

| Setting | What it does |
|---|---|
| **Sensor** | the door or window contact; open counts as `on` |
| **Zones affected** | empty = the whole installation |
| **Delay before suspending** | empty or 0 = the moment it opens |

**A shared appliance follows demand, not silence.** When the same boiler sits
as a source under several zones, it does not stop the moment one of those zones
is suspended: if another zone is asking for heat right then, that demand wins
and the boiler keeps running. A closed system simply has no way to heat one room
and not the other.

For that there is a second field on the openings list screen:

| Field | Meaning |
| --- | --- |
| **Appliances that stop for any opening** | empty = everything stays governed per zone |

Whatever you tick there stops the moment any opening in the installation stands
open, wherever it is and with its own delay — while everything else carries on
being governed per zone. Meant precisely for the boiler: linking that opening to
**every** zone stops the air conditioners in those rooms too, all year round,
while those belong under per-room control. Leave it empty and nothing about how
your installation behaves today changes.

The room then names `opening_open_elsewhere` as its reason, so you can see why
nothing is happening. Two things stay as they always were: a zone under override
and a hand-operated source are not steered, by this list either.

## Step 12 — Save and close

Pick **✅ Save and close** in the main menu. Only then is the installation
written out.

If something is structurally wrong — a zone with no usable source, two sources
on the same entity, an outdoor window that admits nothing — you first get a
list, with the choice *Save anyway* or *Back to change something*. It is a
**warning, not a refusal**: an installation may deliberately be unusual, and
only you know whether it is. The same list also appears under **Repairs** for
as long as it applies.

## What you get in Home Assistant

One device per installation, holding:

| Entity | What for |
|---|---|
| `sensor.*_last_decision` | how many zones are being served, with the full plan as attributes |
| `sensor.*_would_command_<entity>` | the mode the director would put this appliance in — one sensor per appliance |
| `sensor.*_mismatch` | how many appliances currently sit somewhere other than where the plan wants them; 0 = director and house agree |
| `sensor.*_<zone>_source` | which source serves this zone, with what the zone wanted, got and why |
| `binary_sensor.*_<zone>_blocked` | on when a zone got less than it asked for, or wanted to run but a circumstance held it back; the shut gates are in the attributes |
| `binary_sensor.*_<zone>_on_stand_in` | on when a zone runs on a stand-in appliance because its first choice is unreachable |
| `binary_sensor.*_stuck` | on when a zone sits on the same waiting reason too long |
| `switch.*_director` | the master switch; off = nothing is regulated |
| `switch.*_holiday_schedule` | makes every day count as a Saturday, or as its own holiday schedule |
| `switch.*_guest_mode` | keeps regulating while the residents are away |
| `switch.*_<zone>_override` | hands one zone over to you completely |
| `number.*_<zone>_priority` | this zone's precedence; settable from an automation too |
| `number.*_pre_conditioning_duration` | how long one press of a pre-conditioning button lasts |
| `button.*_<zone>_pre_condition` | pre-conditions this zone |

There is also a downloadable diagnostics export with the configuration, the
last snapshot read and the last plan.

## The switches and buttons

- **Master switch** (`switch.*_director`): off = the director does nothing at
  all.
- **Guest mode** (`switch.*_guest_mode`): somebody untracked is staying, so
  "house empty" says nothing. Sleep of those who are home still applies, and
  outside the guest window the ordinary gates take over.
- **Holiday schedule** (`switch.*_holiday_schedule`): every day counts as a
  Saturday, or as its own holiday window. It also switches on by itself once a
  configured calendar has a running event carrying the keyword. Without a
  keyword the calendars are ignored.
- **Override** (`switch.*_<zone>_override`): hands one zone over to you
  completely. The director sends that zone nothing at all — an off included.
  The circuit rules do still apply to the other rooms. It holds until you turn
  it off yourself, through the night and through an empty house as well: it is a
  decision you undo, not tonight's decision. That is what makes it usable to
  leave a zone to automations of your own for days. Switching an appliance off
  at the appliance *itself* does lapse at bedtime or on an empty house; that is
  below.
- **Pre-conditioning button** (`button.*_<zone>_pre_condition`) and **duration**
  (`number.*_pre_conditioning_duration`): see below.

## Actions

| Action | What for |
|---|---|
| `climate_director.evaluate` | decide again right now, without waiting for a state change |
| `climate_director.precondition` | start pre-conditioning |
| `climate_director.cancel_precondition` | call a running pre-conditioning request off |

`climate_director.evaluate` is handy while setting up. In shadow mode it still
executes nothing — it only recomputes.

## Pre-conditioning

The only way to run an empty house, and deliberately the only one you have to
switch on by hand.

- **With a button**: every zone has `button.*_<zone>_pre_condition`. How long
  such a press lasts sits in `number.*_pre_conditioning_duration` (60 minutes by
  default, a quarter of an hour to two hours).
- **With the action**:

  ```yaml
  action: climate_director.precondition
  data:
    zone_ids: [<zone>]
    minutes: 45
  ```

**Important:** you do not say what should happen. The request only opens the
door; after that the integration decides exactly as it would otherwise — the
dead band checks whether it is too cold or too warm, the season and the outdoor
window per source pick the appliance. If the room already sits right, the
appliance stays off.

During a pre-conditioning request the master switch, an override, the dead
band, the season, the outdoor window per source, windows and doors, the circuit
and the exclusive groups all keep applying. Skipped are: *somebody home*,
*awake*, *schedule*, *presence in the room*, the outdoor window per zone and the
quiet window.

An open window or door **refuses** a request. Whoever opened the window may
say: do it anyway.

```yaml
action: climate_director.precondition
data:
  zone_ids: [<zone>]
  minutes: 90
  ignore_openings: true
```

One limit you cannot forget: **it expires by itself.** Ask for longer than the
configured maximum and your request is shortened. Naming no time gives you the
maximum; zero or less is refused, since that is not a request but a typo.

A request always outranks the automation, whatever the hour. Only an open door
asks for confirmation: without *Do it anyway* the door refuses the request.

Call it off with `climate_director.cancel_precondition`.

## Taking charge yourself

- **Switching an appliance off yourself** (at the appliance or on the remote)
  silences that zone. The director does not put it back on two seconds later.
  The zone takes part again once you switch it back on, once everybody who is
  home turns in, or once it is the next day.
- **Switching an appliance on by hand for a few hours** works with a script
  beside it, as long as you hand that zone back to yourself with the override
  for the duration. Without the override the director works out its own plan at
  the next evaluation and switches your appliance off again. An appliance with
  *Start this appliance automatically* off needs no override.
- **A room you always operate yourself**: still make it a zone (otherwise the
  integration does not know that appliance exists), pick the appliance's own
  `climate.*` entity as the indoor sensor, and turn *Start this appliance
  automatically* off on the source.

## Judging a shadow run

Three sensors make a shadow run judgeable afterwards:

- **`sensor.*_mismatch`** is the headline number. Zero means the director agrees
  with whatever is running at that moment. A brief spike is normal; a reading
  that stays up is a real disagreement. Put this sensor in a history graph.
- **`sensor.*_would_command_<entity>`** goes next to the history of the
  `climate` entity it names. Two lines following each other = the director
  decided the same thing your automations did.
- **`sensor.*_<zone>_source`** and **`binary_sensor.*_<zone>_blocked`** then
  tell you *why*: which source was chosen, and which gate held a zone back.

## Blueprints and notifications

Climate Director sends no messages of its own. Where a notification goes, how
it sounds and whether it may arrive at night differs per household. Instead the
integration lays out events and sensors for your own automation to hang on.
Three of them you should not skip:

| Blueprint | Why you cannot do without it | Import link |
|---|---|---|
| **Monitoring** | reports silent failure: a zone that is stuck, or a zone running on a dearer stand-in appliance | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/monitoring.yaml` |
| **Refused pre-conditioning** | you pressed a button and nothing happened; this reports it, with a *Do it anyway* button | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/precondition_refused.yaml` |
| **What was decided** | the handiest tool while configuring and during a shadow run | `https://github.com/Sarnog/ha-climate-director/blob/main/blueprints/automation/climate_director/decisions.yaml` |

Import them through **Settings → Automations and scenes → Blueprints → Import
blueprint**, with the link above.

> **Importing alone is not enough.** A blueprint is a template; nothing listens
> until you build an automation from it. Do that right after importing.

For as long as nobody is listening for a refused pre-conditioning request, Home
Assistant carries a repair notice about it. That disappears by itself once an
automation stands on that event.

## Troubleshooting

- **`binary_sensor.*_stuck`** comes on when a zone sits on the same waiting
  reason too long (15 minutes by default) — and only for that. A full outdoor
  unit does not count: it only frees up once another room stops asking, and that
  may take hours. That room does stand recorded as blocked. The
  `unusable_entities` attribute additionally lists which configured entities
  cannot be read — mistyped, deleted, or temporarily `unavailable`, and a sensor
  that reads fine but yields no number as well (`no number`). That does not
  raise the sensor; a repair notice follows for it after five minutes.
- **`binary_sensor.*_<zone>_on_stand_in`** comes on when a zone runs on a source
  that was not the first choice, because the first choice is unreachable. The
  room simply gets warm — and that is exactly why, without a sensor, you notice
  nothing until the energy bill arrives.
- **Repair notices** under *Repairs* show structural mistakes in the
  configuration. The zones that are sound carry on being regulated; one broken
  zone does not stop the installation.
- **An entity that cannot be read for five minutes** is listed there too, along
  with which ones. That is a mistake in reality rather than in the
  configuration: a sensor with a flat battery, an appliance off the network, or
  an entity that was renamed. The settling time keeps a brief hiccup during a
  restart out of it. It counts especially for an unreadable indoor temperature,
  since the director then leaves a running appliance alone and that appliance
  holds its outdoor unit to its duty.
- **A role asking a mode the appliance cannot run** appears there too, after
  five minutes. Think of a source with the *heating and cooling* role on a unit
  reporting only `heat` and `off`: the director skips it for cooling, and from
  the outside that looks like a room with nothing to do. Check the role under
  *Configure*, or the appliance's `hvac_modes` under *Developer tools*.
- **An appliance that does not carry out its command** reports itself after
  about ten minutes. The director has been asking the same thing all that time
  and the appliance keeps reporting something else: the call is accepted and
  nothing happens, or the appliance puts itself straight back. Check whether the
  appliance is reachable, whether it accepts the mode, and whether something
  else is putting it back — a thermostat schedule or another automation. In
  shadow mode this notice never appears: nothing is executed there on purpose.
- **The diagnostics** (downloadable at the integration) hold the configuration,
  the last snapshot read and the last plan. With those three, any decision is
  exactly reproducible.

## Languages

The explanation under every input follows your Home Assistant's language.
Shipped: Dutch, English, German, French, Spanish and Arabic.

[![Buy me a coffee on Ko-fi](https://img.shields.io/badge/Ko--fi-Buy%20me%20a%20coffee-FF5E5B?style=for-the-badge&logo=kofi&logoColor=white)](https://ko-fi.com/sarnog)
[![Sponsor via GitHub](https://img.shields.io/github/sponsors/sarnog?style=for-the-badge&logo=github&label=Sponsors&color=EA4AAA)](https://github.com/sponsors/sarnog)
