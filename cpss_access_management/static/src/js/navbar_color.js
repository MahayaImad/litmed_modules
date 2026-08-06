/** @odoo-module **/

import { registry } from "@web/core/registry";
import { session } from "@web/session";

/**
 * Colours the navigation bar with the colour of the active company.
 *
 * The active company is read from the `cids` cookie, which is the value the
 * web client itself maintains when the user switches company: reading it
 * keeps the bar in sync with what the client actually sends, without asking
 * the server. The colours themselves travel in the session information, so
 * no round trip is needed at startup either.
 */

const SEPARATEURS_CIDS = /[,-]/;

function lireCookie(nom) {
    const morceaux = `; ${document.cookie}`.split(`; ${nom}=`);
    if (morceaux.length !== 2) {
        return null;
    }
    return decodeURIComponent(morceaux.pop().split(";").shift());
}

function societeActive() {
    // Le cookie fait foi : il reflète le dernier basculement de société.
    const cids = lireCookie("cids");
    if (cids) {
        const premier = parseInt(cids.split(SEPARATEURS_CIDS)[0], 10);
        if (!Number.isNaN(premier)) {
            return premier;
        }
    }
    // Repli au premier chargement, avant que le cookie n'existe.
    const societes = session.user_companies;
    if (!societes) {
        return null;
    }
    const courante = societes.current_company;
    return Array.isArray(courante) ? courante[0] : courante;
}

function couleurSociete(identifiant) {
    const societes = session.user_companies && session.user_companies.allowed_companies;
    if (!societes || !identifiant) {
        return null;
    }
    const societe = societes[identifiant] || societes[String(identifiant)];
    return (societe && societe.navbar_color) || null;
}

/**
 * Noir ou blanc, selon ce qui reste lisible sur la couleur de fond.
 * Luminance perçue pondérée (ITU-R BT.601).
 */
function couleurTexte(couleur) {
    const hexa = couleur.replace("#", "");
    const complet =
        hexa.length === 3
            ? hexa
                  .split("")
                  .map((caractere) => caractere + caractere)
                  .join("")
            : hexa;
    const rouge = parseInt(complet.slice(0, 2), 16);
    const vert = parseInt(complet.slice(2, 4), 16);
    const bleu = parseInt(complet.slice(4, 6), 16);
    if ([rouge, vert, bleu].some(Number.isNaN)) {
        return "#FFFFFF";
    }
    return (rouge * 299 + vert * 587 + bleu * 114) / 1000 > 150
        ? "#111111"
        : "#FFFFFF";
}

function appliquerCouleur(couleur) {
    const racine = document.documentElement;
    if (!couleur) {
        racine.classList.remove("cpss_navbar_color");
        return;
    }
    racine.style.setProperty("--cpss-navbar-color", couleur);
    racine.style.setProperty("--cpss-navbar-text-color", couleurTexte(couleur));
    racine.classList.add("cpss_navbar_color");
}

export const cpssNavbarColorService = {
    start() {
        appliquerCouleur(couleurSociete(societeActive()));
    },
};

registry.category("services").add("cpss_navbar_color", cpssNavbarColorService);
