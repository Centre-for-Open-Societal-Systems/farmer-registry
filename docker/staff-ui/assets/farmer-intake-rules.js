/*
 * Farmer intake: on-the-spot behaviour the platform's widget library lacks.
 *
 * The widget library validates one field at a time as the staff type
 * (pattern, min/max, required) but has no cross-field rules, no computed
 * fields and no calendar other than Gregorian; everything else surfaces as a
 * toast after Next. The domain services enforce these rules on every path
 * and their messages are the source of truth -- this script only tells the
 * enumerator the same thing while the cursor is still in the box:
 *
 *   1. Household: Family Size = males + females, filled in as they type and
 *      flagged inline if edited to something else; children <= family size.
 *   2. Dates: a Gregorian date fills its Ethiopic (EC) twin and vice versa,
 *      for the farmer's birth date and for any table column pair whose
 *      headers end in "(GC)" / "(EC)" (household members, crops, IDs).
 *   3. Photo: a non-image is refused with a message that names what is
 *      accepted, and a large image is resized to 1024px / JPEG before the
 *      widget previews it, so what is shown is what will be uploaded.
 *   4. Geo hierarchy: a level with nothing to choose from (a woreda with no
 *      kebele in Master Data) is hidden instead of an empty dropdown, and the
 *      lowest level is labelled "Village/Kebele" whichever mnemonic the
 *      Master Data pack uses.
 *
 * Injected by the Dockerfile as a plain <script defer> from /public; it walks
 * the DOM (data-widget-id, table headers) rather than the minified React
 * tree, and drives React-controlled inputs through the native value setter
 * plus an input event, which is how React 19 reads user edits.
 */
(function () {
  "use strict";

  var ERR_CLASS = "far-rule-error";

  /* ------------------------------------------------------------ helpers */

  function setNativeValue(input, value) {
    var proto = input instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
    var setter = Object.getOwnPropertyDescriptor(proto, "value").set;
    setter.call(input, value);
    input.dispatchEvent(new Event("input", { bubbles: true }));
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function showError(anchor, key, message) {
    var host = anchor.closest(".table-cell-field") || anchor.closest(".widget-container") || anchor.parentElement;
    if (!host) return;
    var el = host.querySelector("." + ERR_CLASS + "[data-key=\"" + key + "\"]");
    if (!message) {
      if (el) el.remove();
      return;
    }
    if (!el) {
      el = document.createElement("p");
      el.className = ERR_CLASS + " text-xs mt-1 leading-tight";
      el.setAttribute("data-key", key);
      el.setAttribute("role", "alert");
      el.style.color = "var(--toast-failed-color, #DC3545)";
      host.appendChild(el);
    }
    el.textContent = message;
  }

  function widgetInput(sectionId, widgetId) {
    return document.querySelector(
      '.section[data-section-id="' + sectionId + '"] .widget-container[data-widget-id="' + widgetId + '"] input'
    );
  }

  function intValue(input) {
    if (!input) return null;
    var text = String(input.value || "").replace(/,/g, "").trim();
    if (text === "") return null;
    var n = Number(text);
    return Number.isFinite(n) ? n : null;
  }

  /* --------------------------------------------- 1. household family size */

  var HH = "farmer_household_information";
  var hhAutoFilled = false;

  function familySizeRule(changed) {
    var male = widgetInput(HH, "number_of_male_members");
    var female = widgetInput(HH, "number_of_female_members");
    var children = widgetInput(HH, "number_of_children");
    var size = widgetInput(HH, "size_of_group");
    if (!size) return;
    var m = intValue(male), f = intValue(female), c = intValue(children), s = intValue(size);

    if ((changed === male || changed === female) && m !== null && f !== null) {
      // Fill Family Size while it is blank or still holds our own earlier
      // sum; never overwrite something the enumerator typed themselves.
      if (s === null || hhAutoFilled) {
        setNativeValue(size, String(m + f));
        hhAutoFilled = true;
        s = m + f;
      }
    }
    if (changed === size) hhAutoFilled = false;

    var sizeError = "";
    if (s !== null && m !== null && f !== null && s !== m + f) {
      sizeError = "Family Size must equal Number Of Males + Number Of Females (" + m + " + " + f + " = " + (m + f) + ")";
    }
    showError(size, "family-size", sizeError);

    var childError = "";
    if (children && c !== null && s !== null && c > s) {
      childError = "Number Of Children (" + c + ") cannot exceed Family Size (" + s + ")";
    }
    if (children) showError(children, "children", childError);
  }

  /* --------------------------------------------- 2. Gregorian <-> Ethiopic */

  var JD_EPOCH = 1723856; // 1 Meskerem 1 Amete Mihret, as ethiopian_calendar.py

  function gregorianToJdn(y, m, d) {
    var a = Math.floor((14 - m) / 12), yy = y + 4800 - a, mm = m + 12 * a - 3;
    return d + Math.floor((153 * mm + 2) / 5) + 365 * yy + Math.floor(yy / 4) - Math.floor(yy / 100) + Math.floor(yy / 400) - 32045;
  }
  function jdnToGregorian(jdn) {
    var a = jdn + 32044, b = Math.floor((4 * a + 3) / 146097), c = a - Math.floor(146097 * b / 4);
    var d = Math.floor((4 * c + 3) / 1461), e = c - Math.floor(1461 * d / 4), m = Math.floor((5 * e + 2) / 153);
    return [100 * b + d - 4800 + Math.floor(m / 10), m + 3 - 12 * Math.floor(m / 10), e - Math.floor((153 * m + 2) / 5) + 1];
  }
  function ethiopicToJdn(y, m, d) {
    return (JD_EPOCH + 365) + 365 * (y - 1) + Math.floor(y / 4) + 30 * m + d - 31;
  }
  function jdnToEthiopic(jdn) {
    var r = (((jdn - JD_EPOCH) % 1461) + 1461) % 1461;
    var n = (r % 365) + 365 * Math.floor(r / 1460);
    return [4 * Math.floor((jdn - JD_EPOCH) / 1461) + Math.floor(r / 365) - Math.floor(r / 1460), Math.floor(n / 30) + 1, (n % 30) + 1];
  }
  function ethiopicMonthLength(y, m) { return m === 13 ? (y % 4 === 3 ? 6 : 5) : 30; }
  function pad(n) { return (n < 10 ? "0" : "") + n; }

  function gcToEc(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    if (!m) return null;
    var e = jdnToEthiopic(gregorianToJdn(+m[1], +m[2], +m[3]));
    return e[0] + "-" + pad(e[1]) + "-" + pad(e[2]);
  }
  function ecToGc(text) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec((text || "").trim());
    if (!m) return null;
    var y = +m[1], mo = +m[2], d = +m[3];
    if (y < 1 || mo < 1 || mo > 13 || d < 1 || d > ethiopicMonthLength(y, mo)) return "invalid";
    var g = jdnToGregorian(ethiopicToJdn(y, mo, d));
    return g[0] + "-" + pad(g[1]) + "-" + pad(g[2]);
  }

  var syncing = false;
  function syncPair(gc, ec, changed) {
    if (syncing || !gc || !ec) return;
    syncing = true;
    try {
      if (changed === gc) {
        // A date input reports partial years (0001-05-15) while the year is
        // being typed; wait for a plausible one. Only clear an EC value this
        // script filled in itself, never one the enumerator typed.
        var e = /^\d{4}-/.test(gc.value) && gc.value.slice(0, 4) >= "1000" ? gcToEc(gc.value) : null;
        if (gc.value === "" && ec.value !== "" && ec.dataset.farAuto === "1") setNativeValue(ec, "");
        else if (e && ec.value !== e) { setNativeValue(ec, e); ec.dataset.farAuto = "1"; }
        showError(ec, "ec", "");
      } else {
        delete ec.dataset.farAuto;
        var g = ecToGc(ec.value);
        if (ec.value.trim() === "") { if (gc.value !== "" && gc.dataset.farAuto === "1") setNativeValue(gc, ""); showError(ec, "ec", ""); }
        else if (g === "invalid") showError(ec, "ec", "Not a real Ethiopian date (months 1-12 have 30 days, Pagumen has 5 or 6)");
        else if (g === null) showError(ec, "ec", ""); // still typing; the widget's own pattern check speaks on blur
        else { if (gc.value !== g) { setNativeValue(gc, g); gc.dataset.farAuto = "1"; } showError(ec, "ec", ""); }
      }
    } finally {
      syncing = false;
    }
  }

  var BIRTH = "farmer_birth_information";
  function birthPair(changed) {
    syncPair(widgetInput(BIRTH, "birth_date"), widgetInput(BIRTH, "birth_date_ec"), changed);
  }

  // Table rows: cells are positional, so pair columns by their header titles.
  function tablePair(input) {
    var td = input.closest("td"), tr = td && td.parentElement, table = td && td.closest("table");
    if (!td || !table) return;
    // The table widget title-cases its headers ("Date Of Birth (gc)"), so
    // match the calendar tag case-insensitively.
    var headers = Array.prototype.map.call(table.querySelectorAll("thead th"), function (th) { return (th.getAttribute("title") || th.textContent || "").trim().toLowerCase(); });
    var idx = Array.prototype.indexOf.call(tr.children, td);
    var title = headers[idx] || "";
    var m = /^(.*)\((gc|ec)\)\s*$/.exec(title);
    if (!m) return;
    var base = m[1], other = m[2] === "gc" ? "ec" : "gc";
    var otherIdx = headers.indexOf(base + "(" + other + ")");
    if (otherIdx < 0) return;
    var otherInput = tr.children[otherIdx] && tr.children[otherIdx].querySelector("input");
    if (!otherInput) return;
    if (m[2] === "gc") syncPair(input, otherInput, input);
    else syncPair(otherInput, input, input);
  }

  /* ------------------------------------------------------------- 3. photo */

  var PHOTO_MAX_EDGE = 1024;
  var PHOTO_MAX_BYTES = 1024 * 1024;
  var PHOTO_TYPES = { "image/jpeg": 1, "image/png": 1, "image/webp": 1 };
  var PHOTO_HINT = "JPG, PNG or WebP. Larger photos are resized to 1024px automatically.";

  function photoWidget(input) {
    return input.closest('[class*="header-section-widget-"]');
  }

  function photoNote(widget, message, isError) {
    var el = widget.querySelector(".far-photo-note");
    if (!el) {
      el = document.createElement("p");
      el.className = "far-photo-note text-xs mt-1 leading-tight";
      var avatar = widget.querySelector(".hdr-avatar");
      var host = (avatar && avatar.parentElement) || widget;
      host.appendChild(el);
    }
    el.textContent = message;
    el.style.color = isError ? "var(--toast-failed-color, #DC3545)" : "var(--owt-color-text-muted, #727474)";
  }

  function replaceFiles(input, file) {
    var dt = new DataTransfer();
    dt.items.add(file);
    input.files = dt.files;
    input.dataset.farChecked = "1";
    input.dispatchEvent(new Event("change", { bubbles: true }));
  }

  function shrink(file, done) {
    var url = URL.createObjectURL(file), img = new Image();
    img.onload = function () {
      var scale = Math.min(1, PHOTO_MAX_EDGE / Math.max(img.width, img.height));
      var w = Math.round(img.width * scale), h = Math.round(img.height * scale);
      var canvas = document.createElement("canvas");
      canvas.width = w; canvas.height = h;
      canvas.getContext("2d").drawImage(img, 0, 0, w, h);
      URL.revokeObjectURL(url);
      canvas.toBlob(function (blob) {
        var name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
        done(blob ? new File([blob], name, { type: "image/jpeg" }) : null);
      }, "image/jpeg", 0.85);
    };
    img.onerror = function () { URL.revokeObjectURL(url); done(null); };
    img.src = url;
  }

  function photoChange(e) {
    var input = e.target;
    if (!(input instanceof HTMLInputElement) || input.type !== "file") return;
    var widget = photoWidget(input);
    if (!widget) return;
    if (input.dataset.farChecked === "1") { delete input.dataset.farChecked; return; }
    var file = input.files && input.files[0];
    if (!file) return;
    if (!PHOTO_TYPES[file.type]) {
      e.stopImmediatePropagation();
      input.value = "";
      photoNote(widget, "This file is not a photo. Choose a JPG, PNG or WebP image.", true);
      return;
    }
    // Needs resizing: stop the widget previewing the original, resize, then
    // hand it the smaller file through the same picker.
    e.stopImmediatePropagation();
    var needsShrink = file.size > PHOTO_MAX_BYTES;
    var probe = new Image(), probeUrl = URL.createObjectURL(file);
    probe.onload = function () {
      URL.revokeObjectURL(probeUrl);
      if (!needsShrink && Math.max(probe.width, probe.height) <= PHOTO_MAX_EDGE) {
        photoNote(widget, PHOTO_HINT, false);
        replaceFiles(input, file);
        return;
      }
      shrink(file, function (small) {
        if (!small) { input.value = ""; photoNote(widget, "This image could not be read. Choose another JPG, PNG or WebP photo.", true); return; }
        photoNote(widget, "Resized to " + Math.round(small.size / 1024) + " KB for upload.", false);
        replaceFiles(input, small);
      });
    };
    probe.onerror = function () { URL.revokeObjectURL(probeUrl); input.value = ""; photoNote(widget, "This image could not be read. Choose another JPG, PNG or WebP photo.", true); };
    probe.src = probeUrl;
  }

  function photoHints() {
    document.querySelectorAll('[class*="header-section-widget-"] input[type="file"]').forEach(function (input) {
      var widget = photoWidget(input);
      if (widget && !widget.querySelector(".far-photo-note")) photoNote(widget, PHOTO_HINT, false);
    });
  }

  /* ------------------------------------------------- 3b. other file cells */

  var FILE_MAX_TEXT = "up to 10 MB";
  var pickedNames = {};

  function fileNotes() {
    document.querySelectorAll('.widget-container[data-widget-id] input[type="file"]').forEach(function (input) {
      var widget = input.closest(".widget-container");
      if (!widget || widget.closest('[class*="header-section-widget-"]') || widget.querySelector(".far-file-note")) return;
      var accept = (input.getAttribute("accept") || "").split(",").map(function (a) { return a.trim().replace(/^\./, "").toUpperCase(); }).filter(Boolean);
      var note = document.createElement("p");
      note.className = "far-file-note text-xs mt-1 leading-tight";
      note.style.color = "var(--owt-color-text-muted, #727474)";
      // No accept attribute: the registry's document profile applies
      // (png, jpg, jpeg, webp, pdf; 10 MB).
      note.textContent = (accept.length ? accept.join(", ") : "PDF, JPG, PNG or WebP") + ", " + FILE_MAX_TEXT;
      (input.closest(".flex-1") || widget).appendChild(note);
    });
  }

  // The dialog-table shows a picked file in its row as "[object Object]";
  // show the file's name instead (remembered from the picker).
  function rememberPick(input) {
    var widget = input.closest(".widget-container");
    var id = widget && widget.getAttribute("data-widget-id");
    if (id && input.files && input.files[0]) pickedNames[id.replace(/-dlg-\d+-/, "-")] = input.files[0].name;
  }
  function fileCellNames() {
    document.querySelectorAll(".table-widget-container td").forEach(function (td) {
      if (td.textContent.trim() !== "[object Object]") return;
      var names = Object.keys(pickedNames);
      td.textContent = names.length ? pickedNames[names[names.length - 1]] : "Attached file";
    });
  }

  /* --------------------------------------------------------- 4. geo levels */

  function geoLevels() {
    document.querySelectorAll('.widget-container[data-widget-id$="geo_hierarchy"] select').forEach(function (select) {
      var row = select.closest(".mb-\\[10px\\]") || select.parentElement.parentElement;
      if (!row) return;
      var label = row.querySelector("label span, label");
      if (label && /^(village|kebele)$/i.test(label.textContent.trim())) label.textContent = "Village/Kebele";
      // Enabled with only the placeholder means the parent is chosen, the
      // level has loaded, and Master Data holds nothing under it.
      var empty = !select.disabled && select.options.length <= 1;
      row.style.display = empty ? "none" : "";
    });
    document.querySelectorAll('.widget-container[data-widget-id$="geo_hierarchy"] label span').forEach(function (span) {
      if (/^(village|kebele)$/i.test(span.textContent.trim())) span.textContent = "Village/Kebele";
    });
  }

  /* ------------------------------------------------------------- wiring */

  // Runs after React has handled the keystroke: these rules write into other
  // controlled inputs, and doing that before React's own handler for the
  // typed field has committed re-renders the section with that field's store
  // value still stale, wiping what was just typed. Bubble phase plus a tick
  // puts the rule after React's root listener and its state flush.
  function onEdit(e) {
    var t = e.target;
    if (!(t instanceof HTMLInputElement) || t.type === "file") return;
    setTimeout(function () {
      var container = t.closest(".widget-container");
      var section = t.closest(".section");
      var sid = section && section.getAttribute("data-section-id");
      if (sid === HH) familySizeRule(t);
      else if (sid === BIRTH && container) birthPair(t);
      else if (t.classList.contains("table-cell-input")) tablePair(t);
    }, 0);
  }

  document.addEventListener("input", onEdit, false);
  document.addEventListener("change", onEdit, false);
  // The photo check must run BEFORE the widget sees the file, so it can stop
  // the event and hand over a resized one.
  document.addEventListener("change", function (e) {
    if (!(e.target instanceof HTMLInputElement) || e.target.type !== "file") return;
    if (photoWidget(e.target)) photoChange(e);
    else rememberPick(e.target);
  }, true);

  var scheduled = false;
  function refresh() {
    scheduled = false;
    geoLevels();
    photoHints();
    fileNotes();
    fileCellNames();
  }
  new MutationObserver(function () {
    if (!scheduled) { scheduled = true; requestAnimationFrame(refresh); }
  }).observe(document.documentElement, { childList: true, subtree: true, attributes: true, attributeFilter: ["disabled"] });
  refresh();
})();
