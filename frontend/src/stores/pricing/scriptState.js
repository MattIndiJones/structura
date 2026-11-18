// Onglets, script, paramètres déclarés et calendriers CONSTAT.
// Partie du store du Pricer (src/stores/pricing.js), découpé le 18/11/2026.
import { calendarDefaultState, registerCalendarDefaults } from '../../composables/useCalendarDefaults.js'
import { computed, reactive, ref } from 'vue'
import { DEFAULT_SCRIPT, _defaultWindow, _sameNumber } from './helpers.js'

export function installScriptState(s) {
  // ── Tabs ──────────────────────────────────────────────────────────
  const leftTab = ref('script')   // 'script' | 'economics' | 'params' | 'deal' | 'events'
  const rightTab = ref('empty')   // 'empty' | 'results' | 'flux' | 'greeks' | 'profile' | 'paths' | 'proba' | 'backtest' | 'mtf' | 'simulation' | 'scenarios' | 'kid' | 'emt'

  // ── Script ────────────────────────────────────────────────────────
  const script = ref(DEFAULT_SCRIPT)
  const scriptParams = ref([])
  const parseError = ref(null)
  // Validation is a gesture: Ctrl+S, « Valider », or the start of a
  // calculation. Typing never commits a declaration any more — a
  // `PARAM M_KI_BAR = 6` caught before its `0%` used to price a 6 % barrier.
  // `validatedScript` is the text the declarations above describe;
  // `checkedScript` the text of the last attempt, which `parseError` describes.
  const validatedScript = ref('')
  const checkedScript = ref('')
  const scriptDirty = computed(() => script.value !== checkedScript.value)
  // What the last explicit validation changed in Economics: typed values that
  // were replaced, PARAM() rows that were kept. The editor shows it, so that
  // no typed value disappears without saying so.
  const validationReport = ref(null)
  // Years of the `AT 1, 2, 3:` blocks, counted from the strike (empty without one).
  const scriptAtDates = ref([])

  // User-edited PARAM values, keyed by name, in display units (e.g. 8 for "8%").
  // Seeded once per name from the script's declared default. A validated
  // change of that declaration (value or unit) then carries the new value
  // over — see _applyDeclarationChanges; an unchanged declaration never
  // touches what was typed, and neither does a load.
  const paramOverrides = reactive({})
  const parameterConversions = reactive({})
  const parameterShapes = {}

  /**
   * Aligne les surcharges sur ce que le script DÉCLARE, sans rien détruire.
   *
   * Règle du projet : le script déclare des noms, le deal porte les valeurs.
   * Une valeur saisie est une donnée de term sheet, pas une dérivée du texte —
   * une manipulation de texte ne doit donc jamais la détruire.
   *
   * Un nom qui disparaît laisse sa valeur DORMANTE : plus rien ne la lit
   * (`_buildUserParams` et `_buildConstats` parcourent les déclarations, pas
   * les entrées), mais si le nom revient, la valeur revient avec lui. Le coût
   * est de quelques centaines d'octets ; le bénéfice est qu'un renommage par
   * erreur, un copier-coller ou une frappe malheureuse ne coûtent plus une
   * ressaisie de term sheet.
   */
  function _syncParamOverrides() {
    for (const p of scriptParams.value) {
      if (!(p.name in paramOverrides)) {
        // PARAM() → a table of per-observation rows, seeded with one row
        // (the script's optional seed). One row = constant across all
        // observations (the engine extends the last row), so this initial
        // state is immediately priceable.
        paramOverrides[p.name] = p.kind === 'array' ? [p.display_default] : p.display_default
      } else if (p.kind === 'array' && !Array.isArray(paramOverrides[p.name])) {
        // Declaration changed PARAM → PARAM() under a sticky override:
        // promote the scalar to a single-row table instead of crashing the UI.
        paramOverrides[p.name] = parameterShapes[p.name]?.array?.slice() || [paramOverrides[p.name]]
      } else if (p.kind !== 'array' && Array.isArray(paramOverrides[p.name])) {
        parameterShapes[p.name] = { array: [...paramOverrides[p.name]] }
        parameterConversions[p.name] = [...paramOverrides[p.name]]
      }
      if (p.kind === 'array') delete parameterConversions[p.name]
    }
  }

  function confirmParameterConversion(name, index) {
    const values = parameterConversions[name]
    if (!values || !Number.isInteger(index) || index < 0 || index >= values.length) return
    paramOverrides[name] = values[index]
    delete parameterConversions[name]
  }

  /**
   * Carries the declarations the script just changed over to Economics.
   *
   * Decision of 14/09/2026: the last explicit change wins. A PARAM whose
   * initial value or unit changed since the previous validation takes the new
   * value, even over a typed one — and the replaced value is reported. An
   * unchanged declaration touches nothing: validating never erases a typed value.
   *
   * `PARAM()`: only the rows still at the old initial value follow the
   * script; typed rows are kept (M11).
   *
   * New names are not handled here: `_syncParamOverrides` seeds them.
   */
  function _applyDeclarationChanges(before, after) {
    const report = { replaced: [], keptRows: [] }
    const previous = new Map((before || []).map(p => [p.name, p]))
    for (const p of after || []) {
      const old = previous.get(p.name)
      if (!old || !(p.name in paramOverrides)) continue
      if (parameterConversions[p.name]) continue
      if (old.kind !== p.kind) continue
      const unitChanged = !!old.is_pct !== !!p.is_pct
      if (old.required && p.required && !unitChanged) continue
      if (p.required && !unitChanged) continue
      if (!unitChanged && _sameNumber(old.display_default, p.display_default)) continue
      const current = paramOverrides[p.name]
      if (p.kind === 'array') {
        let kept = 0
        paramOverrides[p.name] = (Array.isArray(current) ? current : [current]).map(row => {
          if (_sameNumber(row, old.display_default)) return p.display_default
          kept += 1
          return row
        })
        if (kept) report.keptRows.push({ name: p.name, count: kept, unitChanged })
      } else {
        const value = Array.isArray(current) ? current[0] : current
        paramOverrides[p.name] = p.display_default
        const typed = !_sameNumber(value, old.display_default)
        const unchangedOnScreen = !unitChanged && _sameNumber(value, p.display_default)
        if (typed && !unchangedOnScreen) {
          report.replaced.push({
            name: p.name, before: value, beforePct: !!old.is_pct,
            after: p.display_default, afterPct: !!p.is_pct,
          })
        }
      }
    }
    return report
  }

  // ── CONSTAT calendars ──────────────────────────────────────────────
  // Same "sticky" pattern as paramOverrides: scriptConstats comes straight
  // from /api/parse (name + kind), constatOverrides holds the actual values
  // the user fills in, seeded once per name and never touched again by a
  // re-parse as long as that name still exists in the script.
  const scriptConstats = ref([])   // [{name, kind: 'single'|'schedule'|'nested_schedule'}]
  const scriptHasStop  = ref(false)
  const scriptHasMaturityEvent = ref(false)
  const constatOverrides = reactive({})
  const calendarShapes = {}
  const calendarKinds = {}

  function _defaultConstatValue(kind, reduction = null, scope = 'length') {
    // Une date unique se stocke comme une chaîne — sauf si elle porte une
    // fenêtre, auquel cas il lui faut un objet pour l'accueillir. Le serveur
    // accepte les deux formes.
    if (kind === 'single') {
      if (!reduction) return ''
      const value = reactive({ date: '', ..._defaultWindow(scope) })
      calendarDefaultState(value)
      return value
    }
    const value = reactive({
      start_date: '', first_observation_date: '', period_start_date: '', end_date: '', roll_date: '',
      frequency: { value: null, unit: 'M' }, stub: 'short_last',
      sub_frequency: kind === 'nested_schedule' ? { value: 1, unit: 'M' } : null,
      // Sans ajustement ni décalage par défaut : c'est déjà ce que le parseur
      // suppose faute de valeur, donc rien ne bouge pour un script existant.
      // Un term sheet qui dit autre chose le dit maintenant explicitement.
      convention: 'none', settlement_lag: 0,
      ...(reduction ? _defaultWindow(scope) : {}),
    })
    calendarDefaultState(value)
    return value
  }

  /** Même règle que `_syncParamOverrides` : on complète, on ne supprime pas. */
  function _syncConstatOverrides() {
    for (const c of scriptConstats.value) {
      const previousKind = calendarKinds[c.name]
      if (previousKind && previousKind !== c.kind && c.name in constatOverrides) {
        const old = constatOverrides[c.name]
        calendarShapes[c.name] ||= {}
        calendarShapes[c.name][previousKind] = JSON.parse(JSON.stringify(old))
        const common = typeof old === 'object' && old ? Object.fromEntries(
          ['convention', 'settlement_lag', 'window_length', 'window_frequency',
            'observation_calendars', 'observation_join', 'settlement_calendars', 'settlement_join',
            ...(previousKind !== 'single' && c.kind !== 'single'
              ? ['start_date','first_observation_date','period_start_date','end_date','roll_date','frequency','stub'] : [])]
            .filter(k => k in old).map(k => [k, JSON.parse(JSON.stringify(old[k]))])) : {}
        constatOverrides[c.name] = calendarShapes[c.name][c.kind]
          ? JSON.parse(JSON.stringify(calendarShapes[c.name][c.kind]))
          : Object.assign(c.kind === 'single' ? { date: '' } : _defaultConstatValue(c.kind, c.reduction, c.window_scope), common)
        if (constatOverrides[c.name] && typeof constatOverrides[c.name] === 'object')
          registerCalendarDefaults(constatOverrides[c.name])
      }
      calendarKinds[c.name] = c.kind
      if (!(c.name in constatOverrides)) {
        constatOverrides[c.name] = _defaultConstatValue(c.kind, c.reduction, c.window_scope)
        continue
      }
      // Le script a pu gagner ou perdre sa réduction depuis la dernière frappe.
      // On promeut/rétrograde la valeur collante au lieu de la perdre : c'est la
      // même règle que pour PARAM -> PARAM().
      const v = constatOverrides[c.name]
      if (c.reduction && typeof v === 'string') {
        constatOverrides[c.name] = reactive({ date: v, ..._defaultWindow(c.window_scope) })
      } else if (c.reduction && v && typeof v === 'object' && !v.window_frequency) {
        Object.assign(v, _defaultWindow(c.window_scope))
      } else if (!c.reduction && c.kind === 'single' && v && typeof v === 'object') {
        // Removing a window must not drop the payment convention or lag.
        delete v.window_length; delete v.window_frequency
      }
    }
    s._applyCalendarDefaults()
  }

  const initialFixingName = computed(() => scriptConstats.value.find(c => c.role === 'initial_fixing')?.name || null)
  const startDate = computed({
    get: () => {
      const value = initialFixingName.value ? constatOverrides[initialFixingName.value] : s.globalParams.strike_date
      return typeof value === 'string' ? value : value?.date || ''
    },
    set: value => {
      const name = initialFixingName.value
      if (name) {
        if (constatOverrides[name] && typeof constatOverrides[name] === 'object') constatOverrides[name].date = value
        else constatOverrides[name] = value
      }
      s.globalParams.strike_date = value
    },
  })

  Object.assign(s, { leftTab, rightTab, script, scriptParams, parseError, validatedScript, checkedScript, scriptDirty, validationReport, scriptAtDates, paramOverrides, parameterConversions, parameterShapes, _syncParamOverrides, confirmParameterConversion, _applyDeclarationChanges, scriptConstats, scriptHasStop, scriptHasMaturityEvent, constatOverrides, calendarShapes, calendarKinds, _defaultConstatValue, _syncConstatOverrides, initialFixingName, startDate })
}
