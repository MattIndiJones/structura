#!/usr/bin/env python3
"""Retired direct-Deal demo writer; use the canonical UAT workflow."""
import argparse


def main():
    parser = argparse.ArgumentParser(
        description=("Ce générateur historique est retiré. Utilisez Administration > "
                     "Générateur UAT dans Structura : les lots passent par Product, "
                     "RFQ, Booking et les fixings, avec les modèles PayScript actuels."))
    parser.parse_args()
    parser.exit(2, "Générateur retiré : utilisez Administration > Générateur UAT. "
                   "Aucune donnée n'a été modifiée.\n")


if __name__ == '__main__':
    main()
