/*
 * Coop Schweiz card: shopping list with product suggestions from the Coop
 * catalogue. Served by the coop_schweiz integration.
 *
 *   type: custom:coop-schweiz-card
 *   entity: todo.coop_schweiz_einkaufszettel
 *   title: Einkaufszettel        (optional)
 *   show_completed: true         (optional, default true)
 */
const TEXTS = {
  de: {
    placeholder: "Artikel suchen oder eingeben",
    freeText: "als Freitext hinzufügen",
    done: "Erledigt",
    empty: "Die Liste ist leer.",
    searching: "Suche …",
    noHits: "Kein Treffer im Coop-Sortiment",
    searchFailed: "Die Suche ist gerade nicht möglich",
    error: "Das hat nicht geklappt",
    remove: "Entfernen",
    quantity: "Menge",
    less: "Weniger",
    more: "Mehr",
    noEntity: "Entität nicht gefunden",
  },
  fr: {
    placeholder: "Chercher ou saisir un article",
    freeText: "ajouter comme texte libre",
    done: "Terminé",
    empty: "La liste est vide.",
    searching: "Recherche …",
    noHits: "Aucun résultat dans l'assortiment Coop",
    searchFailed: "La recherche est momentanément impossible",
    error: "Cela n'a pas fonctionné",
    remove: "Supprimer",
    quantity: "Quantité",
    less: "Moins",
    more: "Plus",
    noEntity: "Entité introuvable",
  },
  it: {
    placeholder: "Cerca o inserisci un articolo",
    freeText: "aggiungi come testo libero",
    done: "Completati",
    empty: "La lista è vuota.",
    searching: "Ricerca …",
    noHits: "Nessun risultato nell'assortimento Coop",
    searchFailed: "La ricerca al momento non è possibile",
    error: "Non ha funzionato",
    remove: "Rimuovi",
    quantity: "Quantità",
    less: "Meno",
    more: "Più",
    noEntity: "Entità non trovata",
  },
  en: {
    placeholder: "Search or type a product",
    freeText: "add as free text",
    done: "Done",
    empty: "The list is empty.",
    searching: "Searching …",
    noHits: "No match in the Coop catalogue",
    searchFailed: "The search is not available right now",
    error: "That did not work",
    remove: "Remove",
    quantity: "Quantity",
    less: "Less",
    more: "More",
    noEntity: "Entity not found",
  },
};

const STYLE = `
  :host { display: block; }
  .wrap { padding: 12px 16px 16px; }
  h2 { margin: 4px 0 12px; font-size: 1.25rem; font-weight: 500; }
  .add { position: relative; }
  input[type=text] {
    width: 100%; box-sizing: border-box; padding: 10px 12px; font: inherit;
    color: var(--primary-text-color);
    background: var(--input-fill-color, var(--secondary-background-color));
    border: 1px solid var(--divider-color); border-radius: 8px; outline: none;
  }
  input[type=text]:focus { border-color: var(--primary-color); }
  .suggest {
    position: absolute; z-index: 5; left: 0; right: 0; top: calc(100% + 4px);
    background: var(--card-background-color); border: 1px solid var(--divider-color);
    border-radius: 8px; box-shadow: 0 4px 12px rgba(0,0,0,.25);
    max-height: 340px; overflow-y: auto;
  }
  .row {
    display: flex; align-items: center; gap: 10px; padding: 8px 10px;
    cursor: pointer; border: 0; background: none; width: 100%; text-align: left;
    font: inherit; color: var(--primary-text-color);
  }
  .row:hover, .row.active { background: var(--secondary-background-color); }
  .row img { width: 36px; height: 36px; object-fit: contain; border-radius: 4px; background: #fff; flex: none; }
  .row .name {
    flex: 1; min-width: 0; overflow: hidden; line-height: 1.25;
    display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2;
  }
  .row .sub, .hint { color: var(--secondary-text-color); font-size: .85em; }
  .hint { padding: 8px 10px; }
  ul { list-style: none; margin: 12px 0 0; padding: 0; }
  li { display: flex; align-items: center; gap: 8px; padding: 6px 0; }
  li label { flex: 1; display: flex; align-items: center; gap: 10px; cursor: pointer; min-width: 0; }
  li span { overflow: hidden; text-overflow: ellipsis; }
  li.done span { text-decoration: line-through; color: var(--secondary-text-color); }
  li button.remove {
    border: 0; background: none; color: var(--secondary-text-color); cursor: pointer;
    font-size: 1.1em; padding: 2px 6px; border-radius: 4px;
  }
  li button.remove:hover { color: var(--error-color); }
  .stepper {
    display: flex; align-items: center; flex: none;
    border: 1px solid var(--divider-color); border-radius: 16px;
  }
  .stepper button {
    border: 0; background: none; color: var(--primary-color); cursor: pointer;
    font: inherit; font-size: 1.15em; line-height: 1; width: 30px; height: 28px;
    border-radius: 16px;
  }
  .stepper button:hover:not(:disabled) { background: var(--secondary-background-color); }
  .stepper button:disabled { color: var(--disabled-text-color, var(--secondary-text-color)); cursor: default; opacity: .5; }
  .count { min-width: 22px; text-align: center; font-variant-numeric: tabular-nums; flex: none; }
  li.done .count { color: var(--secondary-text-color); text-decoration: none; }
  input[type=checkbox] { width: 18px; height: 18px; accent-color: var(--primary-color); flex: none; }
  h3 { margin: 14px 0 0; font-size: .9rem; font-weight: 500; color: var(--secondary-text-color); }
  .msg { margin-top: 10px; color: var(--error-color); font-size: .9em; }
  .empty { margin-top: 12px; color: var(--secondary-text-color); }
`;

class CoopSchweizCard extends HTMLElement {
  constructor() {
    super();
    this.attachShadow({ mode: "open" });
    this._items = [];
    this._products = [];
    this._query = "";
    this._active = -1;
    this._searchSeq = 0;
    this._message = "";
    this._searching = false;
    this._searchFailed = false;
    this._open = false;
    this._unsub = undefined;
    this._subscribing = false;
    this._subFailed = false;
    this._subEntity = undefined;
  }

  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find(
      (id) => id.startsWith("todo.") && id.includes("coop")
    );
    return { entity: entity || "todo.coop_schweiz_einkaufszettel" };
  }

  setConfig(config) {
    if (!config || !config.entity || !config.entity.startsWith("todo.")) {
      throw new Error("entity (todo.…) is required");
    }
    const entityChanged = !this._config || this._config.entity !== config.entity;
    this._config = { show_completed: true, ...config };
    if (!this._titleEl) this._build();
    if (entityChanged) {
      this._unsubscribe();
      this._items = [];
      this._message = "";
    }
    this._subFailed = false;
    this._subscribe();
    this._render();
  }

  set hass(hass) {
    const before = this._hass && this._config && this._hass.states[this._config.entity];
    this._hass = hass;
    if (!this._config) return;
    this._subscribe();
    // The list itself arrives through the subscription; only the heading
    // and the "entity missing" state depend on the state object.
    if (before !== hass.states[this._config.entity]) this._render();
  }

  connectedCallback() {
    this._subFailed = false;
    this._subscribe();
  }

  disconnectedCallback() {
    clearTimeout(this._timer);
    clearTimeout(this._blurTimer);
    this._searchSeq++;
    this._unsubscribe();
  }

  getCardSize() {
    return 3 + Math.ceil(this._items.length / 2);
  }

  get _t() {
    const lang = ((this._hass && this._hass.language) || "de").slice(0, 2);
    return TEXTS[lang] || TEXTS.en;
  }

  _unsubscribe() {
    if (this._unsub) {
      try {
        this._unsub();
      } catch (err) {
        // connection already closed
      }
    }
    this._unsub = undefined;
    this._subEntity = undefined;
  }

  // Live list of the to-do items, the same source the built-in card uses.
  _subscribe() {
    if (!this._hass || !this._config || !this.isConnected) return;
    if (this._unsub || this._subscribing || this._subFailed) return;
    const entity = this._config.entity;
    if (!this._hass.states[entity]) return;
    this._subscribing = true;
    this._hass.connection
      .subscribeMessage(
        (msg) => {
          if (this._subEntity !== entity) return;
          this._items = (msg && msg.items) || [];
          this._render();
        },
        { type: "todo/item/subscribe", entity_id: entity }
      )
      .then((unsub) => {
        this._subscribing = false;
        if (!this.isConnected || this._config.entity !== entity) {
          unsub();
          this._subscribe();
          return;
        }
        this._unsub = unsub;
        this._subEntity = entity;
      })
      .catch(() => {
        this._subscribing = false;
        this._subFailed = true;
        this._message = this._t.error;
        this._render();
      });
    // Messages can arrive before the promise resolves.
    this._subEntity = entity;
  }

  _build() {
    const root = this.shadowRoot;
    root.innerHTML = "";
    const style = document.createElement("style");
    style.textContent = STYLE;
    const card = document.createElement("ha-card");
    const wrap = document.createElement("div");
    wrap.className = "wrap";
    this._titleEl = document.createElement("h2");
    const add = document.createElement("div");
    add.className = "add";
    this._input = document.createElement("input");
    this._input.type = "text";
    this._input.autocomplete = "off";
    this._input.addEventListener("input", () => this._onInput());
    this._input.addEventListener("keydown", (ev) => this._onKey(ev));
    this._input.addEventListener("focus", () => {
      clearTimeout(this._blurTimer);
      this._open = true;
      this._renderSuggest();
    });
    this._input.addEventListener("blur", () => {
      // Delay so that a click on a suggestion still arrives.
      clearTimeout(this._blurTimer);
      this._blurTimer = setTimeout(() => {
        if (this.shadowRoot.activeElement === this._input) return;
        this._open = false;
        this._renderSuggest();
      }, 200);
    });
    this._suggestEl = document.createElement("div");
    this._suggestEl.className = "suggest";
    this._suggestEl.hidden = true;
    add.append(this._input, this._suggestEl);
    this._listEl = document.createElement("div");
    this._msgEl = document.createElement("div");
    this._msgEl.className = "msg";
    this._msgEl.setAttribute("role", "status");
    wrap.append(this._titleEl, add, this._msgEl, this._listEl);
    card.append(wrap);
    root.append(style, card);
  }

  _render() {
    if (!this._hass || !this._config || !this._titleEl) return;
    const state = this._hass.states[this._config.entity];
    this._titleEl.textContent =
      this._config.title || (state && state.attributes.friendly_name) || "Coop";
    this._input.placeholder = this._t.placeholder;
    this._input.setAttribute("aria-label", this._t.placeholder);
    const message = state ? this._message : this._t.noEntity;
    this._msgEl.textContent = message;
    this._msgEl.hidden = !message;

    const items = state ? this._items : [];
    const open = items.filter((item) => item.status !== "completed");
    const done = items.filter((item) => item.status === "completed");
    this._listEl.innerHTML = "";
    if (!state) return;
    if (!open.length && !(done.length && this._config.show_completed)) {
      const empty = document.createElement("div");
      empty.className = "empty";
      empty.textContent = this._t.empty;
      this._listEl.append(empty);
      return;
    }
    this._listEl.append(this._list(open, false));
    if (done.length && this._config.show_completed) {
      const heading = document.createElement("h3");
      heading.textContent = `${this._t.done} (${done.length})`;
      this._listEl.append(heading, this._list(done, true));
    }
  }

  _list(items, done) {
    const ul = document.createElement("ul");
    for (const item of items) {
      const li = document.createElement("li");
      if (done) li.className = "done";
      const label = document.createElement("label");
      const box = document.createElement("input");
      box.type = "checkbox";
      box.checked = done;
      box.addEventListener("change", () =>
        this._call("todo", "update_item", {
          item: item.uid,
          status: box.checked ? "completed" : "needs_action",
        })
      );
      // The integration shows quantities as "3× name".
      const match = /^(\d{1,3})× (.+)$/.exec(item.summary || "");
      const quantity = match ? parseInt(match[1], 10) : 1;
      const name = match ? match[2] : item.summary || "";
      const text = document.createElement("span");
      text.textContent = name;
      label.append(box, text);
      li.append(label);

      if (done) {
        if (quantity > 1) {
          const count = document.createElement("span");
          count.className = "count";
          count.textContent = `${quantity}×`;
          li.append(count);
        }
      } else {
        const setQuantity = (value) =>
          this._call("todo", "update_item", {
            item: item.uid,
            rename: value > 1 ? `${value}x ${name}` : name,
          });
        const stepper = document.createElement("div");
        stepper.className = "stepper";
        stepper.setAttribute("role", "group");
        stepper.setAttribute("aria-label", `${this._t.quantity}: ${name}`);
        const minus = document.createElement("button");
        minus.type = "button";
        minus.textContent = "−";
        minus.disabled = quantity <= 1;
        minus.setAttribute("aria-label", this._t.less);
        minus.addEventListener("click", () => setQuantity(quantity - 1));
        const count = document.createElement("span");
        count.className = "count";
        count.textContent = String(quantity);
        const plus = document.createElement("button");
        plus.type = "button";
        plus.textContent = "+";
        plus.disabled = quantity >= 999;
        plus.setAttribute("aria-label", this._t.more);
        plus.addEventListener("click", () => setQuantity(quantity + 1));
        stepper.append(minus, count, plus);
        li.append(stepper);
      }

      const remove = document.createElement("button");
      remove.type = "button";
      remove.className = "remove";
      remove.textContent = "✕";
      remove.title = this._t.remove;
      remove.setAttribute("aria-label", `${this._t.remove}: ${name}`);
      remove.addEventListener("click", () =>
        this._call("todo", "remove_item", { item: [item.uid] })
      );
      li.append(remove);
      ul.append(li);
    }
    return ul;
  }

  async _call(domain, service, data) {
    try {
      await this._hass.callService(domain, service, data, {
        entity_id: this._config.entity,
      });
      this._message = "";
    } catch (err) {
      this._message = (err && err.message) || this._t.error;
    }
    // Shows or clears the message; also resets a checkbox whose change failed.
    this._render();
  }

  _onInput() {
    this._query = this._input.value.trim();
    this._active = -1;
    this._open = true;
    this._searchFailed = false;
    clearTimeout(this._timer);
    this._searchSeq++; // drop the answer of a search that is still running
    if (this._query.length < 2) {
      this._products = [];
      this._searching = false;
      this._renderSuggest();
      return;
    }
    this._searching = true;
    this._renderSuggest();
    this._timer = setTimeout(() => this._search(this._query), 400);
  }

  async _search(query) {
    const seq = ++this._searchSeq;
    let products = [];
    let failed = false;
    try {
      const result = await this._hass.callWS({ type: "coop_schweiz/search", query });
      products = (result.products || []).slice(0, 10);
    } catch (err) {
      failed = true;
    }
    if (seq !== this._searchSeq) return; // a newer input or search took over
    this._products = products;
    this._searching = false;
    this._searchFailed = failed;
    this._renderSuggest();
  }

  _renderSuggest() {
    const box = this._suggestEl;
    box.innerHTML = "";
    if (!this._open || !this._query) {
      box.hidden = true;
      return;
    }
    box.hidden = false;
    // Row 0: the typed text as free text. Rows 1..n: catalogue products.
    const free = document.createElement("button");
    free.type = "button";
    free.tabIndex = -1;
    free.className = "row" + (this._active <= 0 ? " active" : "");
    const freeName = document.createElement("span");
    freeName.className = "name";
    freeName.textContent = `«${this._query}»`;
    const freeSub = document.createElement("span");
    freeSub.className = "sub";
    freeSub.textContent = this._t.freeText;
    free.append(freeName, freeSub);
    free.addEventListener("mousedown", (ev) => ev.preventDefault());
    free.addEventListener("click", () => this._addFreeText());
    box.append(free);

    this._products.forEach((product, index) => {
      const row = document.createElement("button");
      row.type = "button";
      row.tabIndex = -1;
      row.className = "row" + (this._active === index + 1 ? " active" : "");
      const img = document.createElement("img");
      img.loading = "lazy";
      img.alt = "";
      if (typeof product.image === "string" && product.image.startsWith("https://")) {
        img.src = product.image;
      }
      const name = document.createElement("span");
      name.className = "name";
      name.textContent = product.name;
      const sub = document.createElement("span");
      sub.className = "sub";
      sub.textContent = product.content || "";
      row.append(img, name, sub);
      row.addEventListener("mousedown", (ev) => ev.preventDefault());
      row.addEventListener("click", () => this._addProduct(product));
      box.append(row);
    });

    if (this._query.length >= 2 && (this._searching || !this._products.length)) {
      const hint = document.createElement("div");
      hint.className = "hint";
      hint.textContent = this._searching
        ? this._t.searching
        : this._searchFailed
          ? this._t.searchFailed
          : this._t.noHits;
      box.append(hint);
    }
  }

  _onKey(ev) {
    const rows = this._products.length + 1;
    if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
      ev.preventDefault();
      const step = ev.key === "ArrowDown" ? 1 : -1;
      this._open = true;
      this._active = (Math.max(this._active, 0) + step + rows) % rows;
      this._renderSuggest();
    } else if (ev.key === "Enter") {
      ev.preventDefault();
      if (!this._query) return;
      if (this._active > 0) this._addProduct(this._products[this._active - 1]);
      else this._addFreeText();
    } else if (ev.key === "Escape") {
      this._open = false;
      this._renderSuggest();
    }
  }

  _reset() {
    clearTimeout(this._timer);
    this._searchSeq++;
    this._input.value = "";
    this._query = "";
    this._products = [];
    this._active = -1;
    this._searching = false;
    this._searchFailed = false;
    this._renderSuggest();
  }

  async _addFreeText() {
    const text = this._query;
    if (!text) return;
    this._reset();
    await this._call("todo", "add_item", { item: text });
  }

  async _addProduct(product) {
    if (!product) return;
    this._reset();
    await this._call("coop_schweiz", "add_product", { code: product.code, quantity: 1 });
  }
}

if (!customElements.get("coop-schweiz-card")) {
  customElements.define("coop-schweiz-card", CoopSchweizCard);
  window.customCards = window.customCards || [];
  window.customCards.push({
    type: "coop-schweiz-card",
    name: "Coop Schweiz",
    description: "Shopping list with product suggestions from the Coop catalogue",
  });
}
