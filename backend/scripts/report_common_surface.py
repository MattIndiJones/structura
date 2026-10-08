"""Render the completed offline comparison as French Markdown and a plot."""
import json
import math
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backend.app.core.volatility_surface import SSVISurface

OUT=ROOT/'output/common-surface-20261007'
LABELS={'constant':'GBM','heston':'Heston','sabr':'SABR','localvol':'Local Vol','lsv':'LSV'}


def number(value,digits=4):
    return f'{value:.{digits}f}'.replace('.',',')


def main():
    report=json.loads((OUT/'autocalls.json').read_text())
    convergence=json.loads((OUT/'convergence.json').read_text())
    precision=json.loads((OUT/'precision.json').read_text())
    target=SSVISurface(**report['surface']['parameters'])
    lines=['# Autocall quatre ans — cible commune sans arbitrage — 07/10/2026','',
    'Les dix prix sont calculés avec les mêmes conventions contractuelles et une cible SSVI synthétique.',
    '**Les contrôles numériques passent dans le régime testé. La reproduction de la cible reste approximative pour Heston et insuffisante pour SABR à paramètres constants.**',
    'Leurs prix ci-dessous sont des valorisations de ces ajustements paramétriques ; leurs écarts aux autres modèles ne mesurent pas uniquement le risque de dynamique.',
    'Local Vol et LSV reproduisent la même cible dans la tolérance du contrôle ; leur comparaison est la plus directement interprétable.',
    '', '## Payoff et hypothèses', '',
    '- Coupon cumulé de 10 % par observation, payé uniquement au rappel à 100 %, y compris au dernier constat.',
    '- Quatre observations annuelles ; protection européenne à 60 %. Sans rappel : capital 1 et put vendu séparé, sans coupon.',
    '- StartDate et value date : 06/10/2026 ; observations 06/10/2027, 06/10/2028, 08/10/2029 et 07/10/2030.',
    '- Paiements : 11/10/2027, 11/10/2028, 11/10/2029 et 10/10/2030, soit J+3 ouvrés TARGET.',
    '- Taux 3 %, dividendes continus 2 % par actif, corrélation des browniens de spot 50 %, EUR, sans funding ni quanto.',
    '- Mono Société Générale ; worst-of Société Générale / STMicro : identités de scénario, avec la même surface synthétique pour les deux actifs. Aucune donnée de marché de ces titres.',
    '', '## Surface et calibration', '',
    'SSVI en log-moneyness forward : `theta(t)=0.04*t`, `rho=-0.75`, `phi(theta)=0.85/sqrt(0.04+theta)`, horizon certifié cinq ans.',
    'Les conditions suffisantes de Gatheral-Jacquier sont vérifiées sur tout cet horizon et pour tous les strikes : borne de pente 0,6073 < 4, borne de courbure 1,0537 < 4 ; variance totale croissante à log-moneyness forward fixe.',
    'Référence : [Gatheral et Jacquier, Arbitrage-free SVI volatility surfaces](https://arxiv.org/abs/1204.0646). Les dérivées de Dupire sont analytiques ; aucune aile polynomiale ni fallback silencieux.',
    '', '| Strike / S0 | Vol cible 1 an | Vol cible 4 ans |', '|---|---:|---:|']
    import numpy as np
    for k in (.6,.8,1.,1.2):
        vols=[100*math.sqrt(float(target.derivatives(math.log(k)-.01*t,t)[0])/t) for t in (1.,4.)]
        lines.append(f'| {number(k*100,0)} % | {number(vols[0])} % | {number(vols[1])} % |')
    lines+=['','Le niveau de 20 % est l’ATM **forward** ; le strike égal au spot initial a une vol légèrement différente à cause du carry.',
            '', '| Modèle | Paramètres ajustés | Reproduction de cible |','|---|---|---|']
    h=report['calibration']['heston']['parameters'];s=report['calibration']['sabr']['parameters']
    lines += [f"| Heston | v0={h['v0']:.6f}, theta={h['theta']:.6f}, kappa={h['kappa']:.6f}, xi={h['xi']:.6f}, rho={h['rho_h']:.6f} | Ajustement approximatif |",
        f"| SABR | alpha={s['alpha']:.6f}, beta={s['beta']:.6f}, rho={s['rho']:.6f}, nu={s['nu']:.6f} | Insuffisante ; beta atteint sa borne haute |",
        '| Local Vol | Dupire analytique de SSVI | Contrôle MC de reproduction satisfait |',
        '| LSV | Cible Dupire SSVI et variance du Heston ajusté | Contrôle MC de reproduction satisfait |',
        '| GBM | Sigma constant 20 % | Référence ATM, sans ajustement du smile |','',
        'Heston est ajusté en prix avec pondération vega et contrôlé par Fourier indépendant. SABR est initialisé par Hagan puis ajusté sur les options OTM du Monte Carlo réellement simulé : 6 000 paires, 104 pas/an, graine 353. La validation finale utilise huit autres graines et une PDE indépendante aux paramètres ajustés.',
        '', '| Modèle | Écart maximal vanille modèle / cible | Écart maximal digital modèle / cible |',
        '|---|---:|---:|']
    for model in ('heston','sabr'):
        r=next(x for x in report['runs'] if x['assets']==1 and x['model']==model)
        lines.append(f"| {LABELS[model]} | {number(r['calibration_max_error_bp']['call'],2)} bps | {number(r['calibration_max_error_bp']['digital'],2)} bps |")
    lines += ['','Il s’agit d’écarts de **calibration** : ils persistent quand les simulateurs retrouvent correctement les prix de leur propre modèle. Les IC Monte Carlo ci-dessous ne les incluent pas.',
        '', '## Prix et incertitude', '',
        '| Modèle | Mono (% nominal) | IC95 mono | Worst-of (% nominal) | IC95 worst-of |',
        '|---|---:|---|---:|---|']
    for model in LABELS:
        a=next(x for x in report['runs'] if x['assets']==1 and x['model']==model)
        b=next(x for x in report['runs'] if x['assets']==2 and x['model']==model)
        lines.append(f"| {LABELS[model]} | {number(a['price_pct'])} | {number(a['ci95_pct'][0])}–{number(a['ci95_pct'][1])} | {number(b['price_pct'])} | {number(b['ci95_pct'][0])}–{number(b['ci95_pct'][1])} |")
    lines += ['', '208 pas/an ; huit graines indépendantes : 42, 17, 93, 731, 2026, 77, 123 et 991. Chaque batch contient 20 000 paires en mono, 10 000 en multi, soit 320 000 / 160 000 trajectoires au total par modèle.',
        'IC95 calculés entre batches avec Student à sept degrés de liberté, afin de prendre en compte la dépendance entre particules LSV. Ils restent estimés sur huit réplications ; ils ne couvrent ni le biais de calibration ni le risque de modèle.',
        '', '## Flux séparés et rappels', '',
        'Toutes les trajectoires paient exactement une jambe de capital. Capital + coupons + put réconcilient chaque prix à l’arrondi flottant.',
        '', '| Cas | Modèle | PV capital | PV coupons | PV put vendu | Rappel avant maturité |',
        '|---|---|---:|---:|---:|---:|']
    for r in report['runs']:
        p=r['pv_legs_pct'];case='Mono' if r['assets']==1 else 'Worst-of'
        lines.append(f"| {case} | {LABELS[r['model']]} | {number(p['capital'])} % | {number(p['coupons'])} % | {number(p['put'])} % | {number(r['early_recall_probability_pct'],2)} % |")
    lines += ['', 'Les probabilités de rappel par observation et les flux par date de paiement sont dans le JSON de résultats.',
        '', '## Comparaison à cible reproduite : LSV / Local Vol', '',
        'Les mêmes graines et browniens de spot sont utilisés dans cette différence ; son incertitude est calculée entre les huit différences de batches.']
    for r in report['matched_surface_comparisons']:
        lines.append(f"- {'Mono' if r['assets']==1 else 'Worst-of'} : LSV − Local Vol = {number(r['change_bp'],2)} bps ; IC95 {number(r['ci95_bp'][0],2)} à {number(r['ci95_bp'][1],2)} bps.")
    lines += ['','En multi, la différence inclut aussi la dynamique de dépendance : une corrélation de browniens identique ne fixe pas une copule terminale identique.',
        '', '## Contrôles et limites', '',
        '- Réserves numériques initiales : huit batches de 25 000 paires sur deux actifs, contrôles aux maturités 6 mois / 1 an, 52 / 104 / 208 pas/an. Tolérances préalables : 2 bps vanille et 10 bps digital, plus trois erreurs standards entre batches. Aucun point signalé à 208 pas/an pour SABR natif et LSV plat.',
        '- Validation des paramètres ajustés : 450 calls, 450 puts et 450 digitaux sur les cinq moteurs mono / marginales multi. Références propres : BS, Fourier Heston, PDE spot SABR, SSVI pour LV/LSV. Aucun point signalé sur cette grille.',
        '- PDE SABR ajusté : raffinement et extension de domaine vérifiés ; enveloppe numérique ajoutée au seuil MC. Les résultats de convergence figurent dans le JSON.',
        '- Contrôle de prix : 104 → 208 pas/an avec browniens couplés sur l’union des deux grilles, huit batches de 5 000 paires, seuil 5 bps plus trois erreurs standards de la différence.',
        '', '| Cas | Modèle | Variation 208 − 104 | SE de la différence | Signalé |',
        '|---|---|---:|---:|---|']
    for r in convergence['runs']:
        lines.append(f"| {'Mono' if r['assets']==1 else 'Worst-of'} | {LABELS[r['model']]} | {number(r['change_bp'],2)} bps | {number(r['change_se_bp'],2)} bps | {'Oui' if r['flagged'] else 'Non'} |")
    lines += ['', 'Les dates de constatation sont quantifiées sur les grilles de simulation. La maturité du produit est atteinte exactement et les flux sont actualisés aux dates contractuelles de paiement. Les fractions d’année effectives des vanilles sont conservées et utilisées dans leurs références.',
        'Le contrôle temporel emploie de petits batches LSV : il ne remplace pas une étude exhaustive de convergence en nombre de particules. Les batches de précision initiale et de pricing final utilisent également des régimes de variance différents, explicitement conservés dans les résultats.',
        '', '## Livraison et reproduction', '',
        'Livraison sous forme d’un benchmark hors interface : cible analytique réutilisable, calibration, contrôles et calcul indépendant des flux sur les simulateurs de production. Le pas de temps par défaut de l’application reste 52/an ; ces prix utilisent explicitement 208/an. La surface n’est pas un nouveau formulaire du Pricer et ces calibrations ne sont pas injectées dans des deals.',
        'Le moteur LSV conserve désormais sa résolution conditionnelle lorsque le benchmark fournit une grille locale plus large. Le chemin historique sur [0,2 ; 3] reste à 200 buckets, vérifié par les goldens.',
        '**29 tests ciblés passent** : six contrôles nouveaux SSVI/payoff, treize contrôles du lot précédent et dix goldens de modèles. Aucune suite backend complète, aucun changement frontend, aucune base réelle utilisée.',
        '', '```powershell',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage precision',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage calibration',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage reference',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage pricing',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage convergence',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/compare_common_surface.py --stage finalize',
        '.venv/Scripts/python.exe -X utf8 backend/scripts/report_common_surface.py', '```', '',
        '- [Cible SSVI](../../backend/app/core/volatility_surface.py)',
        '- [Programme de comparaison](../../backend/scripts/compare_common_surface.py)',
        '- [Prix, flux, probabilités et références](../../output/common-surface-20261007/autocalls.json)',
        '- [Calibration](../../output/common-surface-20261007/calibration.json)',
        '- [Précision native](../../output/common-surface-20261007/precision.json)',
        '- [Convergence des prix](../../output/common-surface-20261007/convergence.json)',
        '- [Graphique](../../output/common-surface-20261007/comparison.png)', '',
        'La suite pertinente pour une comparaison plus stricte est d’améliorer la reproduction des digitaux par les modèles paramétriques, particulièrement SABR, puis d’intégrer un choix explicite de surface et de précision dans le workflow de l’application. Les dix prix actuels restent associés aux hypothèses et réserves ci-dessus.']
    (ROOT/'docs/audits/AUTOCALL_SURFACE_COMMUNE_2026-10-07.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(1,2,figsize=(12,4.5),layout='constrained')
    strikes=np.linspace(.4,1.5,150)
    for t in (1.,4.):
        vol=np.sqrt(target.derivatives(np.log(strikes)-.01*t,t)[0]/t)
        axes[0].plot(strikes*100,vol*100,label=f'{t:g} an(s)')
    axes[0].set(xlabel='Strike / spot initial (%)',ylabel='Volatilité implicite (%)',title='Cible actions SSVI synthétique')
    axes[0].legend();axes[0].grid(alpha=.2)
    x=np.arange(5)
    for assets,offset,label in ((1,-.13,'Mono'),(2,.13,'Worst-of')):
        rows=[r for r in report['runs'] if r['assets']==assets]
        values=np.array([r['price_pct'] for r in rows]);half=np.array([(r['ci95_pct'][1]-r['ci95_pct'][0])/2 for r in rows])
        axes[1].errorbar(x+offset,values,yerr=half,fmt='o',capsize=3,label=label)
    axes[1].set_xticks(x,list(LABELS.values()))
    axes[1].set(ylabel='Prix (% nominal)',title='Autocall 4 ans — IC95 Monte Carlo')
    axes[1].legend();axes[1].grid(alpha=.2)
    fig.suptitle('Heston / SABR : ajustements approximatifs ; GBM : référence à vol constante',fontsize=10)
    fig.savefig(OUT/'comparison.png',dpi=180)
    plt.close(fig)


if __name__=='__main__':
    main()
