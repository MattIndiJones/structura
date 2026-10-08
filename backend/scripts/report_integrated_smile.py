"""Render the completed integrated-smile study, keeping failures visible."""
import json
from pathlib import Path
import sys

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from backend.app.core.volatility_surface import TermSSVISurface

OUT = ROOT/'output/integrated-smile-20261007'
LABELS = dict(constant='Constant / GBM', heston='Heston', sabr='SABR spot', localvol='Local Vol', lsv='LSV')


def load(name):
    return json.loads((OUT/(name+'.json')).read_text(encoding='utf-8'))


def number(value, digits=2):
    return f'{value:.{digits}f}'.replace('.', ',')


def main():
    results, calibration, convergence, api = [load(name) for name in ('results', 'calibration', 'convergence', 'api')]
    verification = load('verification-results')
    verification_flags = sum(sum(r['numerical_flags'].values()) for r in verification['runs'])
    temporal_lv = load('temporal-lv')
    assert len(results['runs']) == 20 and len(convergence['runs']) == 40
    assert len(verification['runs']) == 2 and len(temporal_lv['runs']) == 4
    assert all(r['pairs_per_batch']==(20000 if r['assets']==1 else 10000) for r in results['runs'])
    flags = sum(sum(r['numerical_flags'].values()) for r in results['runs'])
    forward_flags = sum(sum(x['flagged'] for x in r['forward']) for r in results['runs'])
    temporal_flags = sum(r['flagged'] for r in convergence['runs'])
    initial = load('initial-results')
    initial_flags = sum(sum(r['numerical_flags'].values()) for r in initial['runs'])
    count = sum(len(r['validation']) for r in results['runs'])
    lines = ['# Recette quantitative des profils intégrés — autocall 4 ans — 07/10/2026', '',
        '**Le chemin de pricing API et les flux se réconcilient sur les 20 cas.**',
        f'Les contrôles numériques donnent {flags} points signalés sur {count} calls, {count} puts et {count} digitaux ; '
        f'{forward_flags} contrôles de forward et {temporal_flags} contrôles temporels sont signalés.',
        f'La réplication indépendante ciblée des alertes multi, avec 20 000 paires par batch et huit nouvelles graines, '
        f'donne {verification_flags} point signalé sur 80 calls, 80 puts et 80 digitaux. Les alertes de la passe principale restent visibles ci-dessous.',
        'Les écarts de calibration Heston/SABR restent distincts de ces contrôles et de l’incertitude Monte Carlo.', '',
        '## Périmètre et produit', '',
        'Reprise du scénario précédent, avec les profils réellement fabriqués par `frontend/src/utils/volSurface.js`, '
        'la calibration du service `smile_calibration.py`, les schémas Pydantic et la grille LV/LSV de production '
        '`_build_lv_grid`. Aucune grille de surface externe n’est injectée dans la simulation.', '',
        '- Athena quatre ans : coupon cumulé de 10 % par observation, payé au rappel à 100 %, y compris au quatrième constat.',
        '- Sans rappel : capital 1, put vendu européen sous 60 %, sans coupon. Capital, coupons et put sont des flux distincts.',
        '- StartDate = value date : 06/10/2026, conservée pour la comparaison. Observations : 06/10/2027, 06/10/2028, 08/10/2029, 07/10/2030.',
        '- Paiements J+3 ouvrés TARGET : 11/10/2027, 11/10/2028, 11/10/2029, 10/10/2030. Actualisation aux paiements.',
        '- EUR ; taux plat 3 %, dividende continu plat 2 %, funding nul, aucun quanto ou taux stochastique.',
        '- Mono SG ; worst-of SG/STMicro, browniens de spot corrélés à 50 %. Les deux actifs reçoivent la même surface hypothétique.',
        '- Actions ATM 30 % : défaut sans estimation de niveau. Actions ATM 20 % : contrôle au niveau de l’ancienne étude.',
        '- Aucune acquisition de cotation d’options ou de données Yahoo ; les tickers désignent le scénario, pas une calibration de ces titres.', '',
        '## Surface réellement utilisée', '',
        'Piliers ATM 3 mois, 6 mois, 1, 2, 3, 5, 7 et 10 ans, initialement plats. '
        'Profil Actions : ρ = −0,75, η = 0,85, échelle 0,04 ; variance totale ATM croissante et certification SSVI sur 10 ans. '
        'Le niveau entre dans θ(t) et modifie donc aussi la forme relative du smile.', '',
        '| Niveau ATM forward | K/F | Vol 1 an | Vol 4 ans |', '|---|---:|---:|---:|']
    for scenario in calibration['scenarios']:
        target = TermSSVISurface(scenario['surface'])
        for k in (.6, .8, 1., 1.2, 1.4):
            lines.append(f"| {scenario['level']} % | {number(k*100,0)} % | {number(float(target.implied_vol(k,1))*100)} % | {number(float(target.implied_vol(k,4))*100)} % |")
    lines += ['', 'Le tableau ci-dessus est en strike/forward, comme l’éditeur. Les vanilles de contrôle sont en strike/spot initial ; leur référence inclut le carry de 1 %.', '',
        '[Graphique des surfaces et des prix avec IC95](../../output/integrated-smile-20261007/comparison.png)', '',
        '## Résultats à 208 pas/an', '',
        'Huit batches indépendants de 20 000 paires antithétiques en mono et 10 000 en multi, graines 42, 17, 93, 731, 2026, 77, 123 et 991 : '
        '320 000 / 160 000 trajectoires par cas, y compris LSV. Les IC95 utilisent Student à sept degrés de liberté entre batches, '
        'pour inclure la dépendance entre particules LSV. Les écarts au constant utilisent les différences par batch avec les mêmes browniens.', '']
    for level in (30, 20):
        lines += [f'### Actions — ATM {level} %', '',
            '| Modèle | Mono (% nominal) | IC95 mono | Δ constant (points) | Worst-of (% nominal) | IC95 worst-of | Δ constant (points) |',
            '|---|---:|---|---:|---:|---|---:|']
        for model in LABELS:
            a, b = [next(r for r in results['runs'] if r['level']==level and r['assets']==assets and r['model']==model) for assets in (1,2)]
            lines.append(f"| {LABELS[model]} | {number(a['price_pct'],4)} | {number(a['ci95_pct'][0],4)}–{number(a['ci95_pct'][1],4)} | {number(a['change_vs_constant_pct'],4)} | {number(b['price_pct'],4)} | {number(b['ci95_pct'][0],4)}–{number(b['ci95_pct'][1],4)} | {number(b['change_vs_constant_pct'],4)} |")
        lines += ['', '| Cas / modèle | PV capital | PV coupons | PV put vendu | Rappel avant maturité |', '|---|---:|---:|---:|---:|']
        for r in [x for x in results['runs'] if x['level']==level]:
            p=r['pv_legs_pct']
            recall=sum(f['recall'] for f in r['flows'][:3])*100
            lines.append(f"| {'Mono' if r['assets']==1 else 'Worst-of'} / {LABELS[r['model']]} | {number(p['capital'],4)} % | {number(p['coupons'],4)} % | {number(p['put'],4)} % | {number(recall)} % |")
        for assets in (1,2):
            lv=next(r for r in results['runs'] if r['level']==level and r['assets']==assets and r['model']=='localvol')
            lines.append(f"\nLocal Vol {'mono' if assets==1 else 'worst-of'} : Δ constant = {number(lv['change_vs_constant_pct'],4)} point ; IC95 de la différence {number(lv['change_ci95_pct'][0],4)} à {number(lv['change_ci95_pct'][1],4)} point.")
        lines.append('')
    lines += ['## Pourquoi l’effet du smile varie avec le niveau', '',
        'La jambe put vendue devient plus coûteuse avec l’aile gauche. Mais le smile modifie aussi les rappels, '
        'les coupons reçus et la date de remboursement du capital. Le prix de la note est la somme de ces trois PV ; '
        'le coût supplémentaire du put ne mesure donc pas à lui seul l’écart au constant.', '',
        '| ATM | Cas | Δ PV capital LV − GBM | Δ PV coupons | Δ PV put vendu | Δ prix total |',
        '|---|---|---:|---:|---:|---:|']
    for level in (30,20):
        for assets in (1,2):
            base=next(r for r in results['runs'] if r['level']==level and r['assets']==assets and r['model']=='constant')
            lv=next(r for r in results['runs'] if r['level']==level and r['assets']==assets and r['model']=='localvol')
            differences={kind: lv['pv_legs_pct'][kind]-base['pv_legs_pct'][kind] for kind in ('capital','coupons','put')}
            lines.append(f"| {level} % | {'Mono' if assets==1 else 'Worst-of'} | {number(differences['capital'],4)} pt | {number(differences['coupons'],4)} pt | {number(differences['put'],4)} pt | {number(lv['change_vs_constant_pct'],4)} pt |")
    lines += ['', 'Ces mesures concernent ce payoff et cette famille de profils. La forme relative du smile s’atténue avec '
        'le niveau et la maturité ; aucun écart de prix fixé à l’avance n’est ajouté au moteur.', '',
        'Local Vol et LSV visent les mêmes marginales vanilles. Cela ne fixe pas leur dépendance entre dates, '
        'ni la perte conditionnelle à l’absence de rappel. Leur différence sur l’autocall peut donc subsister '
        'même lorsque les contrôles de vanilles et de digitaux passent. En multi, une même corrélation de browniens '
        'ne fixe pas non plus la même dépendance terminale.', '',
        '## Calibration et validations indépendantes', '',
        '| ATM | Modèle | Erreur vanille annoncée au fit | Max vanille modèle / cible, contrôle indépendant | Max digital modèle / cible |', '|---|---|---:|---:|---:|']
    for scenario in calibration['scenarios']:
        for model in ('heston','sabr'):
            r=next(r for r in results['runs'] if r['level']==scenario['level'] and r['assets']==1 and r['model']==model)
            lines.append(f"| {scenario['level']} % | {LABELS[model]} | {number(scenario['fits'][model]['max_price_error_bp'])} bps | {number(r['calibration_max_error_bp']['call'])} bps | {number(r['calibration_max_error_bp']['digital'])} bps |")
    lines += ['', 'Un optimiseur qui converge ne certifie pas la reproduction du smile. Heston ajuste cinq paramètres constants par Fourier ; '
        'SABR ajuste quatre paramètres par Monte Carlo avec 3 000 paires, 104 pas/an et graine 353. '
        'Le contrôle final utilise d’autres graines et une PDE SABR indépendante : il mesure aussi le bruit et le biais de cet ajustement.', '',
        f'La première passe, à 10 000 paires par batch dans les deux dimensions, signalait {initial_flags} points de vanilles/digitaux, '
        'dont certains sous GBM. Le nombre de paires a ensuite été doublé pour **tous** les modèles mono et les deux niveaux, '
        'avec conservation des premières estimations dans `initial-pricing.json` et `initial-results.json`. '
        'Les graines, seuils, paramètres et références restent identiques. Les tableaux présentent cette seconde passe en mono ; '
        'aucune alerte finale n’est supprimée.', '',
        'Références : Black-Scholes pour GBM, Fourier adaptatif pour Heston, PDE spot/log-alpha pour SABR, prix et dérivée de strike SSVI pour LV/LSV. '
        'Les digitaux sont des cash puts sous le strike. Maturités : les quatre temps de grille effectivement observés ; strikes/spot initial : 60, 80, 100, 120 et 150 %. '
        'Tolérances : 2 bps vanille, 10 bps digital, plus trois erreurs standards entre batches ; pour SABR, ajout de l’enveloppe de raffinement et d’extension de domaine PDE.', '',
        '| ATM | Cas | Modèle | Calls signalés | Puts signalés | Digitaux signalés | Forward signalé |', '|---|---|---|---:|---:|---:|---:|']
    for r in results['runs']:
        f=r['numerical_flags']
        lines.append(f"| {r['level']} % | {'Mono' if r['assets']==1 else 'Worst-of'} | {LABELS[r['model']]} | {f['call']} | {f['put']} | {f['digital']} | {sum(x['flagged'] for x in r['forward'])} |")
    lines += ['', '### Réplication indépendante des alertes multi à 30 %', '',
        'GBM et Local Vol sont recalculés à 208 pas/an avec huit batches de 20 000 paires et les nouvelles graines '
        '4242, 1717, 9393, 731731, 20262026, 7777, 123123 et 991991. Aucun seuil ni paramètre de modèle n’est changé. '
        'Le premier essai à 30 000 paires a été refusé par la limite mémoire du calcul ; le budget est respecté avec 20 000.', '',
        '| Modèle | Actif | Maturité effective | Strike / S0 | Écart call initial | Seuil initial | Écart call réplication | Seuil réplication | Signal réplication |',
        '|---|---:|---:|---:|---:|---:|---:|---:|---|']
    for r in results['runs']:
        for row in r['validation']:
            if not row['call']['flagged']: continue
            repeat=next((x for x in verification['runs'] if x['level']==r['level'] and x['assets']==r['assets'] and x['model']==r['model']), None)
            if repeat is None: continue
            new=next(x for x in repeat['validation'] if (x['asset'],x['strike'],x['expiry'])==(row['asset'],row['strike'],row['expiry']))['call']
            old=row['call']
            lines.append(f"| {LABELS[r['model']]} | {row['asset']} | {number(row['expiry'],6)} | {number(row['strike']*100,0)} % | {number(old['error_bp'],3)} bps | {number(2+3*old['batch_se']*10000,3)} bps | {number(new['error_bp'],3)} bps | {number(2+3*new['batch_se']*10000,3)} bps | {'Oui' if new['flagged'] else 'Non'} |")
    lines += ['', 'Les prix multi de cette réplication sont GBM '
        f"{number(verification['runs'][0]['price_pct'],4)} % et Local Vol {number(verification['runs'][1]['price_pct'],4)} %, "
        'compatibles avec les estimations principales. Les petites alertes initiales sont cohérentes avec du bruit statistique ; '
        'une réplication sans alerte ne constitue pas une preuve universelle d’absence de biais.', '']
    lines += ['', '### Convergence temporelle du prix', '',
        'Huit batches de 3 000 paires. Browniens couplés sur l’union des grilles 52/104/208 ; mêmes paiements contractuels. '
        'Signal si |variation| > 5 bps + 3 SE. Ce seuil est un contrôle statistique, pas une garantie d’un biais inférieur à 5 bps.', '',
        '| ATM | Cas | Modèle | 208 − 52 (bps) | SE (bps) | Signal | 208 − 104 (bps) | SE (bps) | Signal |', '|---|---|---|---:|---:|---|---:|---:|---|']
    for r in [x for x in convergence['runs'] if x['coarse_sy']==52]:
        fine=next(x for x in convergence['runs'] if x['level']==r['level'] and x['assets']==r['assets'] and x['model']==r['model'] and x['coarse_sy']==104)
        lines.append(f"| {r['level']} % | {'Mono' if r['assets']==1 else 'Worst-of'} | {LABELS[r['model']]} | {number(r['change_bp'])} | {number(r['se_bp'])} | {'Oui' if r['flagged'] else 'Non'} | {number(fine['change_bp'])} | {number(fine['se_bp'])} | {'Oui' if fine['flagged'] else 'Non'} |")
    lines += ['', 'Local Vol à 30 % est ensuite revérifié avec **10 000 paires par batch**, pour réduire l’incertitude '
        'des écarts de discrétisation observés. Les deux grilles grossières sont comparées à 208 pas/an avec les mêmes seuils.', '',
        '| Cas | Grille grossière | 208 − grille grossière | SE | Signal |', '|---|---:|---:|---:|---|']
    for r in temporal_lv['runs']:
        lines.append(f"| {'Mono' if r['assets']==1 else 'Worst-of'} | {r['coarse_sy']} | {number(r['change_bp'])} bps | {number(r['se_bp'])} bps | {'Oui' if r['flagged'] else 'Non'} |")
    lines += ['', '## Recette d’intégration et limites', '',
        f'- {len(api["runs"])} calculs par appel direct de `price_endpoint`, au défaut applicatif de 52 pas/an, 3 000 paires : '
        'capital total égal à 1, réconciliation des PV et accord avec une évaluation indépendante des flux sur les mêmes diffusions à moins de 10⁻⁶.',
        '- 12 repricings supplémentaires, au défaut de 52 pas/an et 10 000 paires, utilisent les fonctions d’édition de la courbe : '
        'translation de tous les piliers ATM de +1 point et déplacement de la poignée 80 % de +1 point de vol à 1 an. '
        'La translation modifie GBM et LV ; l’aile modifie LV et laisse exactement GBM inchangé, en mono comme en multi. '
        'Valeurs et variations mesurées dans `edits.json` ; cela valide les fonctions et leur consommation, pas un nouveau geste dans le navigateur.',
        '- 9 tests backend ciblés de surface et 11 tests frontend ciblés de surface/calibration passent. Les profils Actions/Indices, '
        'l’édition de courbe/cellule et les conversions RFQ sont couverts par ces tests ; aucune nouvelle recette navigateur effectuée dans cette étude.',
        '- La base réelle reste inchangée. Aucun serveur lancé, aucune suite backend complète, aucun commit ni push.',
        '- Les prix affinés à 208 pas/an viennent des diffusions de production et d’un calcul indépendant du payoff ; '
        'le contrôle API à 52 établit leur cohérence avec PayScript. Le réglage de l’application reste 52 pas/an.',
        '- Les IC95 ne couvrent ni le résidu de calibration, ni le biais numérique, ni le risque de modèle ou de corrélation. '
        'Une même corrélation de browniens ne fixe pas la même dépendance terminale entre modèles.',
        '- Le profil Indices est vérifié par les tests ciblés, mais les 20 prix de cette étude concernent le profil Actions ; '
        'ni pricing résiduel, ni Greeks, ni courbes non plates ne sont recettés quantitativement ici.',
        '- La largeur du smile et le payoff déterminent l’effet mesuré. Une baisse de plusieurs points en Local Vol n’est pas imposée comme résultat attendu.', '',
        '## Reproduction', '', 'Depuis la racine du dépôt, Python du venv avec `-X utf8` :', '', '```powershell',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage calibration',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage api',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage pricing',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage references',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage convergence',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage finalize',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage refine-mono',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage merge-refinement',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage finalize',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage edits',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage verification',
        '.venv/Scripts/python.exe -X utf8 -c "from backend.scripts.study_integrated_smile import finalize; finalize(\'verification\', \'verification-results\')"',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/study_integrated_smile.py --stage temporal-lv',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/report_integrated_smile.py', '```', '',
        'Les requêtes, surfaces, paramètres, receipts, flux, prix par batch, références PDE, seuils, contrôles '
        'et empreintes des sources sont conservés dans `output/integrated-smile-20261007/`. Les anciennes études restent intactes.', '']
    (ROOT/'docs/audits/RECETTE_SMILE_INTEGRE_2026-10-07.md').write_text('\n'.join(lines), encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig, axes=plt.subplots(2,2,figsize=(12,8),layout='constrained')
    for row, level in enumerate((30,20)):
        scenario=next(x for x in calibration['scenarios'] if x['level']==level)
        target=TermSSVISurface(scenario['surface'])
        strikes=np.linspace(.5,1.5,120)
        for expiry in (1.,4.):
            axes[row,0].plot(strikes*100,target.implied_vol(strikes,expiry)*100,label=f'{expiry:g} an(s)')
        axes[row,0].axhline(level,color='grey',linestyle='--',label='Constant ATM')
        axes[row,0].set(xlabel='Strike / forward (%)',ylabel='Vol implicite (%)',title=f'Actions — ATM {level} %')
        for assets,offset,label in ((1,-.12,'Mono'),(2,.12,'Worst-of')):
            runs=[next(r for r in results['runs'] if r['level']==level and r['assets']==assets and r['model']==model) for model in LABELS]
            axes[row,1].errorbar(np.arange(5)+offset,[r['price_pct'] for r in runs],
                yerr=[(r['ci95_pct'][1]-r['ci95_pct'][0])/2 for r in runs],fmt='o',capsize=3,label=label)
        axes[row,1].set_xticks(np.arange(5),['GBM','Heston','SABR','Local Vol','LSV'])
        axes[row,1].set(ylabel='Prix (% nominal)',title=f'Autocall 4 ans — ATM {level} % — IC95 MC')
        for ax in axes[row]: ax.grid(alpha=.2); ax.legend()
    fig.suptitle('Profils intégrés • Hypothèses synthétiques • Heston/SABR : ajustements imparfaits')
    fig.savefig(OUT/'comparison.png',dpi=180)
    plt.close(fig)
    print('REPORT',flags,'numerical flags;',forward_flags,'forward flags;',temporal_flags,'temporal flags')


if __name__=='__main__': main()
