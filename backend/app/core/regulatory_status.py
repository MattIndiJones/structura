"""Regulatory status carried by every KID and EMT the application produces.

Both documents are desk tools, not regulatory deliverables: the KID's VEV is
the module's own approximation of the PRIIPs RTS expression and its scenarios
come from a risk-neutral simulation; the EMT is a target-market aid, not a
FinDatEx-conformant export. The screens already say so. The server says it too,
so that a figure read through the API or from an archive keeps its status.
"""

KID_STATUS = "INDICATIVE_NON_PRIIPS"
KID_NOTICE = (
    "Document indicatif : méthode de Catégorie 3 du règlement délégué 2017/653 "
    "implémentée (bootstrap historique, VaR 97,5 %, scénarios, tension, coûts), sans "
    "validation indépendante, sans correction quanto ni sous-jacent de type courbe, "
    "composition des coûts simplifiée — non conforme PRIIPs à ce titre, à ne pas "
    "diffuser comme KID réglementaire.")

EMT_STATUS = "INDICATIVE_NON_FINDATEX"
EMT_NOTICE = (
    "Aide de desk indicative — pas un export EMT FinDatEx conforme ni un document "
    "réglementaire final : type de client, marché cible et distribution restent à "
    "valider par le producteur.")


def kid_status() -> dict:
    return {"methodology_status": KID_STATUS, "regulatory_notice": KID_NOTICE}


def emt_status() -> dict:
    return {"methodology_status": EMT_STATUS, "regulatory_notice": EMT_NOTICE}
