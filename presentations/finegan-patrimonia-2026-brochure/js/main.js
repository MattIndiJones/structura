(function () {
  "use strict";

  // Renseigner uniquement avec des coordonnées validées avant diffusion.
  const CONTACT_NAME = "";
  const CONTACT_TITLE = "";
  const CONTACT_EMAIL = "";
  const CONTACT_PHONE = "";
  const CONTACT_URL = "https://finegan.fr/#contact";

  const pageTemplates = ["page1", "page2", "page3", "page4"];
  const readingView = document.getElementById("readingView");
  const bookletView = document.getElementById("bookletView");
  const impositionView = document.getElementById("impositionView");
  const printSheets = document.getElementById("printSheets");

  function clonePage(id) {
    return document.getElementById(id).content.firstElementChild.cloneNode(true);
  }

  function makeMarks(sheet) {
    [
      "crop-v crop-top-left-v", "crop-h crop-top-left-h",
      "crop-v crop-top-right-v", "crop-h crop-top-right-h",
      "crop-v crop-bottom-left-v", "crop-h crop-bottom-left-h",
      "crop-v crop-bottom-right-v", "crop-h crop-bottom-right-h",
      "fold-mark fold-top", "fold-mark fold-bottom"
    ].forEach((className) => {
      const mark = document.createElement("span");
      mark.className = className.includes("fold") ? className : `crop-mark ${className}`;
      mark.setAttribute("aria-hidden", "true");
      sheet.appendChild(mark);
    });
  }

  function makeSheet(leftId, rightId, label) {
    const group = document.createElement("div");
    group.className = "screen-sheet-group";
    group.innerHTML = `<div class="screen-sheet-label">${label}</div><div class="sheet-preview"></div>`;
    const sheet = document.createElement("div");
    sheet.className = "sheet";
    const left = clonePage(leftId);
    const right = clonePage(rightId);
    left.classList.add("left-panel");
    right.classList.add("right-panel");
    sheet.append(left, right);
    makeMarks(sheet);
    group.querySelector(".sheet-preview").appendChild(sheet);
    return group;
  }

  function makePrintSheet(leftId, rightId) {
    const sheet = document.createElement("section");
    sheet.className = "sheet";
    const left = clonePage(leftId);
    const right = clonePage(rightId);
    left.classList.add("left-panel");
    right.classList.add("right-panel");
    sheet.append(left, right);
    makeMarks(sheet);
    return sheet;
  }

  function makeBooklet() {
    const intro = document.createElement("div");
    intro.className = "booklet-intro";
    intro.innerHTML = "<span>SIMULATION DU DOCUMENT PLIÉ</span><h2>Une couverture A5, une double page intérieure, un dos.</h2><p>Le pli central sépare les deux expertises sans interrompre la lecture.</p>";

    const inside = document.createElement("div");
    inside.className = "booklet-block booklet-inside";
    inside.innerHTML = '<div class="booklet-label"><b>02–03</b><span>Carnet ouvert · double page intérieure</span></div><div class="booklet-spread"><div class="booklet-page booklet-left"></div><div class="booklet-page booklet-right"></div><i class="booklet-crease"></i></div>';
    inside.querySelector(".booklet-left").appendChild(clonePage("page2"));
    inside.querySelector(".booklet-right").appendChild(clonePage("page3"));

    const outside = document.createElement("div");
    outside.className = "booklet-covers";
    outside.innerHTML = '<div class="booklet-block"><div class="booklet-label"><b>01</b><span>Carnet fermé · couverture</span></div><div class="booklet-closed booklet-front"></div></div><div class="booklet-block"><div class="booklet-label"><b>04</b><span>Carnet retourné · dos</span></div><div class="booklet-closed booklet-back"></div></div>';
    outside.querySelector(".booklet-front").appendChild(clonePage("page1"));
    outside.querySelector(".booklet-back").appendChild(clonePage("page4"));

    bookletView.append(intro, inside, outside);
  }

  function populatePages() {
    pageTemplates.forEach((id) => {
      const wrapper = document.createElement("div");
      wrapper.className = "page-preview";
      wrapper.appendChild(clonePage(id));
      readingView.appendChild(wrapper);
    });
    impositionView.append(
      makeSheet("page4", "page1", "RECTO · PAGE 4 | PAGE 1"),
      makeSheet("page2", "page3", "VERSO · PAGE 2 | PAGE 3")
    );
    printSheets.append(
      makePrintSheet("page4", "page1"),
      makePrintSheet("page2", "page3")
    );
    makeBooklet();
  }

  function populateContacts(root) {
    root.querySelectorAll("[data-contact-details]").forEach((node) => {
      const rows = [];
      if (CONTACT_NAME) rows.push(`<strong>${CONTACT_NAME}</strong>`);
      if (CONTACT_TITLE) rows.push(`<span>${CONTACT_TITLE}</span>`);
      if (CONTACT_EMAIL) rows.push(`<a href="mailto:${CONTACT_EMAIL}">${CONTACT_EMAIL}</a>`);
      if (CONTACT_PHONE) rows.push(`<a href="tel:${CONTACT_PHONE.replace(/\s/g, "")}">${CONTACT_PHONE}</a>`);
      node.innerHTML = rows.join("");
    });

    root.querySelectorAll("[data-contact-url]").forEach((node) => {
      if (CONTACT_URL) node.setAttribute("href", CONTACT_URL);
    });

  }

  function fitPreviews() {
    const pageWidth = 561.26;
    const maxPageWidth = Math.min(window.innerWidth < 860 ? window.innerWidth - 20 : (window.innerWidth - 100) / 2, pageWidth);
    document.documentElement.style.setProperty("--preview-scale", Math.min(1, maxPageWidth / pageWidth).toFixed(4));

    const sheetWidth = 1145.2;
    const maxSheetWidth = Math.max(320, window.innerWidth - 40);
    document.documentElement.style.setProperty("--sheet-scale", Math.min(1, maxSheetWidth / sheetWidth).toFixed(4));

    const bookletWidth = 1122.52;
    const maxBookletWidth = Math.max(300, Math.min(1120, window.innerWidth - 80));
    document.documentElement.style.setProperty("--booklet-scale", Math.min(.86, maxBookletWidth / bookletWidth).toFixed(4));
    document.documentElement.style.setProperty("--cover-scale", Math.min(.58, maxBookletWidth / 1120).toFixed(4));
  }

  function setView(view) {
    readingView.hidden = view !== "reading";
    bookletView.hidden = view !== "booklet";
    impositionView.hidden = view !== "imposition";
    document.querySelectorAll("[data-view]").forEach((button) => {
      const active = button.dataset.view === view;
      button.classList.toggle("is-active", active);
      button.setAttribute("aria-pressed", String(active));
    });
    fitPreviews();
  }

  populatePages();
  populateContacts(document);
  fitPreviews();

  document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => setView(button.dataset.view)));
  document.getElementById("printButton").addEventListener("click", () => window.print());
  window.addEventListener("resize", fitPreviews, { passive: true });
})();
