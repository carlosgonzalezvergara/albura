import streamlit as st
import graphviz
import streamlit.components.v1 as components
import re
import base64
from pathlib import Path

st.set_page_config(
    page_title="Albura - RRG LSC Diagram Assistant",
    layout="wide",
    initial_sidebar_state="collapsed"
)

OP_ABBR = {
    "Aspect": "ASP",
    "Negation": "NEG",
    "Directionals": "DIR",
    "Event quantification": "EVQ",
    "Modality": "MOD",
    "Status": "STA",
    "Tense": "TNS",
    "Evidentiality": "EVID",
    "Illocutionary force": "IF",
}

# --- STATE (for true reset on "New") ---
if "form_id" not in st.session_state:
    st.session_state["form_id"] = 0


def reset_state():
    st.session_state["form_id"] += 1


def get_key(base_name):
    return f"{base_name}_{st.session_state['form_id']}"


#=====================
# DRAWING FUNCTION
#=====================
def draw_lsc_tree(data):
    # Retrieve data
    prdp = data.get("prdp")
    prcs = data.get("prcs")
    items_pre = data.get("items_pre", [])
    items_post = data.get("items_post", [])
    pocs = data.get("pocs")
    podp = data.get("podp")

    pred_type = data.get("pred_type", "verbal")
    nucleus = data.get("nucleus", {})
    nuc_word = nucleus.get("text", "")
    nuc_pos = nucleus.get("pos", "")

    copula = data.get("copula", {})
    cop_word = copula.get("text", "")
    cop_pos = copula.get("pos", "")

    attribute = data.get("attribute", {})
    attr_word = attribute.get("text", "")
    attr_pos = attribute.get("pos", "")

    items_between = data.get("items_between", [])

    # Realization forms
    realization_forms = data.get("realization_forms", [])

    # Extra-Core Slots
    extra_core_slots = data.get("extra_core_slots", [])

    def is_morph(item):
        return item.get("arg_type") == "Morphological"

    def morph_form(item):
        return (item.get("morph_form") or "").strip()

    def is_affix_morph(item):
        # legacy empty -> treat as Affix
        return is_morph(item) and (morph_form(item) == "" or morph_form(item) == "Affix")

    def is_clitic_morph(item):
        return is_morph(item) and morph_form(item) == "Clitic"

    # Detect if we need COREw/NUCw:
    # -> should exist whenever there is ANY morphological argument (Affix or Clitic)
    has_morphological = any(
        is_morph(item) for item in (items_pre + items_post + items_between)
    )

    # Map reference codes -> node IDs
    reference_to_node = {}

    dot = graphviz.Digraph(comment="LSC")

    # GRAPH SETTINGS
    dot.attr(dpi="72")
    dot.attr(splines="line", nodesep="0.4", ranksep="0.25", margin="0")
    dot.attr("node", fontname="Helvetica", fontsize="11", height="0.2", width="0.2")
    dot.attr("edge", fontname="Helvetica", arrowhead="none", penwidth="0.8")

    # ALIGNMENT LISTS (filled during build; final order computed at the end)
    layer_cl = {"pre": [], "center": ["CL"], "post": []}
    layer_core = {"pre": [], "center": ["CORE"], "post": []}
    layer_nuc = {"pre": [], "center": [], "post": []}

    terminal_words = []
    ordered_bottom = []

    # Store tops of morph args for alignment with NUCw (includes AFF and CL)
    morph_arg_top_nodes = []

    # Row-node -> word-node mapping (for vertical alignment ordering)
    row_node_to_word = {}

    # 1) SPINE
    dot.node("S", "SENTENCE", shape="plaintext", fontname="Helvetica", group="main")
    dot.node("CL", "CLAUSE", shape="plaintext", fontname="Helvetica", group="main")
    dot.node("CORE", "CORE", shape="plaintext", fontname="Helvetica", group="main")

    dot.edge("S:s", "CL:n", weight="100")
    dot.edge("CL:s", "CORE:n", weight="100")

    # 2) WORD DRAWER
    def draw_word_structure(parent_id, item, uid):
        word_id = f"{uid}_W"
        dot.node(word_id, item["text"], shape="none", group=uid)

        if item.get("pos"):
            pos_id = f"{uid}_P"
            dot.node(pos_id, item["pos"], shape="plaintext", fontsize="10", group=uid)
            dot.edge(f"{parent_id}:s", f"{pos_id}:n", weight="100")
            dot.edge(f"{pos_id}:s", f"{word_id}:n", weight="100")
        else:
            dot.edge(f"{parent_id}:s", f"{word_id}:n", weight="100")

        return word_id

    # For postprocessing SVG dashed operator-links
    pending_op_connections = []

    # OPERATORS PROJECTION
    def draw_operator_projection(anchor_word_id, operators, ref_to_node):
        if not operators:
            return

        ops_by_layer = {"NUC": [], "CORE": [], "CLAUSE": []}
        for op in operators:
            layer = op.get("layer")
            if layer in ops_by_layer:
                ops_by_layer[layer].append(op)

        def op_text(op):
            op_name = (op.get("operator") or "").strip()
            abbr = OP_ABBR.get(op_name, op_name)
            val = (op.get("value") or "").strip()
            return f"{abbr}: {val}" if val else f"{abbr}"

        global_op_index = [0]

        def build_layer_stack(layer_name):
            stack = []
            ops = ops_by_layer[layer_name]
            n = max(1, len(ops))

            for i in range(n):
                layer_id = f"OP_{layer_name}_{i}"
                dot.node(layer_id, layer_name, shape="plaintext", fontsize="11", group="op_layer")

                if i < len(ops):
                    lbl_id = f"{layer_id}_LBL"
                    dot.node(lbl_id, op_text(ops[i]), shape="plaintext", fontsize="11", group="op_lbl")

                    side = (ops[i].get("side") or "Right").strip()

                    base_minlen = 1
                    increment = 1
                    current_minlen = str(base_minlen + global_op_index[0] * increment)
                    global_op_index[0] += 1

                    with dot.subgraph() as s:
                        s.attr(rank="same")
                        s.node(layer_id)
                        s.node(lbl_id)
                        if side == "Left":
                            s.edge(lbl_id, layer_id, style="invis", weight="50", minlen=current_minlen)
                        else:
                            s.edge(layer_id, lbl_id, style="invis", weight="50", minlen=current_minlen)

                    if side == "Left":
                        dot.edge(f"{lbl_id}:e", f"{layer_id}:w", arrowhead="vee", penwidth="0.8", constraint="false")
                    else:
                        dot.edge(f"{lbl_id}:w", f"{layer_id}:e", arrowhead="vee", penwidth="0.8", constraint="false")

                    target_codes = ops[i].get("targets", [])
                    if target_codes:
                        target_node_ids = []
                        for tc in target_codes:
                            node_id = ref_to_node.get(tc)
                            if node_id:
                                target_node_ids.append(node_id)
                        if target_node_ids:
                            pending_op_connections.append(
                                {"lbl_id": lbl_id, "target_node_ids": target_node_ids, "side": side, "layer": layer_name}
                            )

                stack.append(layer_id)

            for j in range(len(stack) - 1):
                dot.edge(stack[j] + ":s", stack[j + 1] + ":n", weight="100")

            return stack

        nuc_stack = build_layer_stack("NUC")
        core_stack = build_layer_stack("CORE")
        clause_stack = build_layer_stack("CLAUSE")

        sent_id = "OP_SENTENCE"
        dot.node(sent_id, "SENTENCE", shape="plaintext", fontsize="11", group="op_layer")

        dot.edge(anchor_word_id + ":s", nuc_stack[0] + ":n", weight="100")
        dot.edge(nuc_stack[-1] + ":s", core_stack[0] + ":n", weight="100")
        dot.edge(core_stack[-1] + ":s", clause_stack[0] + ":n", weight="100")
        dot.edge(clause_stack[-1] + ":s", sent_id + ":n", weight="100")

    # 3) SLOT DRAWER (PrDP/PrCS/PoCS/PoDP/ExCS)
    def draw_slot(uid, data_dict, parent, target_list, ref_code=None, show_uid_label=True, parent_edge_constraint=True):
        if not data_dict or not data_dict.get("text"):
            return None

        lbl_id = f"{uid}_L"
        w_id = f"{uid}_W"
        row_node_id = None

        if show_uid_label:
            dot.node(uid, uid, shape="plaintext", group=uid)
            dot.edge(f"{parent}:s", f"{uid}:n", weight="1")
            dot.node(lbl_id, data_dict.get("label", "XP"), shape="plaintext", group=uid)
            dot.edge(f"{uid}:s", f"{lbl_id}:n", weight="100")
            row_node_id = uid
        else:
            dot.node(lbl_id, data_dict.get("label", "XP"), shape="plaintext", group=uid)
            dot.edge(
                f"{parent}:s",
                f"{lbl_id}:n",
                weight="1",
                constraint="true" if parent_edge_constraint else "false",
            )
            row_node_id = lbl_id

        dot.node(w_id, data_dict["text"], shape="none", group=uid)

        if data_dict.get("pos"):
            pos_id = f"{uid}_P"
            dot.node(pos_id, data_dict["pos"], shape="plaintext", fontsize="10", group=uid)
            dot.edge(f"{lbl_id}:s", f"{pos_id}:n", weight="100")
            dot.edge(f"{pos_id}:s", f"{w_id}:n", weight="100")
        else:
            dot.edge(f"{lbl_id}:s", f"{w_id}:n", weight="100")

        terminal_words.append(w_id)

        if target_list is not None:
            target_list.append(row_node_id)

        # Row -> word alignment mapping
        if row_node_id:
            row_node_to_word[row_node_id] = w_id

        if ref_code:
            reference_to_node[ref_code] = w_id

        return w_id

    # ------------- NUCLEUS presence flags -------------
    has_nuc = (pred_type == "verbal" and nuc_word) or (pred_type == "copular" and attr_word)

    # Anchor for clitics: PoS under PRED if available, else PRED
    def get_clitic_anchor_id():
        if not has_nuc:
            return "CORE"
        if pred_type == "verbal":
            return "NucP" if nuc_pos else "PRED"
        return "AttrP" if attr_pos else "PRED_A"

    # 4) ITEMS PROCESSOR (pre/post arguments/peripheries)
    def process_item_group(items, side_prefix):
        last_conn_type = None
        current_peri_parent = None

        for i, item in enumerate(items):
            if not item.get("text"):
                continue

            uid = f"{side_prefix}_{i}"
            conn_type = item.get("conn_type")

            if conn_type == "Arg":
                last_conn_type = None
                current_peri_parent = None

                top_id = f"{uid}_Top"

                if is_morph(item):
                    forced_lbl = "AFF" if is_affix_morph(item) else "CL"
                    dot.node(top_id, forced_lbl, shape="plaintext", group=uid)
                else:
                    dot.node(top_id, item.get("label", "XP"), shape="plaintext", group=uid)

                # Decide anchor
                if is_clitic_morph(item):
                    parent_anchor = get_clitic_anchor_id()
                elif is_morph(item):
                    parent_anchor = "COREw" if (has_nuc and has_morphological) else "CORE"
                else:
                    parent_anchor = "CORE"

                # IMPORTANT: do NOT let morphological (AFF/CL) anchors constrain horizontal layout
                dot.edge(
                    f"{parent_anchor}:s",
                    f"{top_id}:n",
                    weight="1",
                    constraint="false" if is_morph(item) else "true",
                )

                # Horizontal ordering:
                # - Only syntactic args participate in NUC-row ordering
                if not is_morph(item):
                    if side_prefix == "Pre":
                        layer_nuc["pre"].append(top_id)
                    else:
                        layer_nuc["post"].append(top_id)

                # Morph args (AFF and CL) should align with NUCw
                if is_morph(item):
                    morph_arg_top_nodes.append(top_id)

                wid = draw_word_structure(top_id, item, uid)
                terminal_words.append(wid)
                ordered_bottom.append(wid)

                row_node_to_word[top_id] = wid
                reference_to_node[f"{side_prefix.lower()}_{i}"] = wid

            else:
                # Periphery
                if conn_type == last_conn_type and current_peri_parent:
                    parent_id = current_peri_parent
                    uid_for_group = f"{side_prefix}_{i}"
                else:
                    parent_id = f"PERI_Group_{uid}"
                    dot.node(parent_id, "PERIPHERY", shape="plaintext", group=uid)
                    uid_for_group = uid

                    target_layer_id = ""
                    if conn_type == "Peri-Clause":
                        target_layer_id = "CL"
                        (layer_cl["pre"] if side_prefix == "Pre" else layer_cl["post"]).append(parent_id)
                    elif conn_type == "Peri-Core":
                        target_layer_id = "CORE"
                        (layer_core["pre"] if side_prefix == "Pre" else layer_core["post"]).append(parent_id)
                    elif conn_type == "Peri-Nuc":
                        target_layer_id = "NUC"
                        (layer_nuc["pre"] if side_prefix == "Pre" else layer_nuc["post"]).append(parent_id)

                    src, tgt = (":e", ":w") if side_prefix == "Pre" else (":w", ":e")
                    dot.edge(
                        f"{parent_id}{src}",
                        f"{target_layer_id}{tgt}",
                        arrowhead="vee",
                        constraint="false",
                        minlen="1",
                    )

                    last_conn_type = conn_type
                    current_peri_parent = parent_id

                item_top_id = f"{uid}_Top"
                dot.node(item_top_id, item.get("label", "XP"), shape="plaintext", group=uid_for_group)
                dot.edge(f"{parent_id}:s", f"{item_top_id}:n", weight="100")

                wid = draw_word_structure(item_top_id, item, uid_for_group)
                terminal_words.append(wid)
                ordered_bottom.append(wid)

                if parent_id and parent_id not in row_node_to_word:
                    row_node_to_word[parent_id] = wid

                reference_to_node[f"{side_prefix.lower()}_{i}"] = wid

    # DRAW SLOTS (topics/foci)
    w_prdp = draw_slot("PrDP", prdp, "S", layer_cl["pre"], "prdp")
    if w_prdp:
        ordered_bottom.append(w_prdp)

    w_prcs = draw_slot("PrCS", prcs, "CL", layer_core["pre"], "prcs")
    if w_prcs:
        ordered_bottom.append(w_prcs)

    nucleus_anchor = None

    # NUCLEUS
    if has_nuc:
        layer_nuc["center"].append("NUC")
        dot.node("NUC", "NUC", shape="plaintext", group="main")
        dot.edge("CORE:s", "NUC:n", weight="100")

        # COREw / NUCw should exist if there is ANY morphological argument
        if has_morphological:
            dot.node(
                "COREw",
                label="<<font face='Helvetica'>CORE<sub>W</sub></font>>",
                shape="plaintext",
                fontsize="10",
                group="main",
            )
            dot.node(
                "NUCw",
                label="<<font face='Helvetica'>NUC<sub>W</sub></font>>",
                shape="plaintext",
                fontsize="10",
                group="main",
            )

        # Pre items
        process_item_group(items_pre, "Pre")

        if pred_type == "verbal":
            dot.node("PRED", "PRED", shape="plaintext", fontsize="10", group="main")
            dot.node("NucW", nuc_word, shape="none", group="main")
            dot.edge("NUC:s", "PRED:n", weight="100")

            if has_morphological:
                if nuc_pos:
                    dot.node("NucP", nuc_pos, shape="plaintext", fontsize="10", group="main")
                    dot.edge("PRED:s", "NucP:n", weight="100")
                    dot.edge("NucP:s", "COREw:n", weight="100")
                    dot.edge("COREw:s", "NUCw:n", weight="100")
                    dot.edge("NUCw:s", "NucW:n", weight="100")
                else:
                    dot.edge("PRED:s", "COREw:n", weight="100")
                    dot.edge("COREw:s", "NUCw:n", weight="100")
                    dot.edge("NUCw:s", "NucW:n", weight="100")
            else:
                if nuc_pos:
                    dot.node("NucP", nuc_pos, shape="plaintext", fontsize="10", group="main")
                    dot.edge("PRED:s", "NucP:n", weight="100")
                    dot.edge("NucP:s", "NucW:n", weight="100")
                else:
                    dot.edge("PRED:s", "NucW:n", weight="100")

            terminal_words.append("NucW")
            ordered_bottom.append("NucW")

            reference_to_node["nucleus"] = "NucW"
            nucleus_anchor = "NucW"

        elif pred_type == "copular":
            nuc_level_order = []

            if cop_word:
                dot.node("AUX", "AUX", shape="plaintext", fontsize="10", group="aux_group")
                dot.node("AuxW", cop_word, shape="none", group="aux_group")

                # IMPORTANT: keep AUX connected but do NOT let it pull the horizontal spine
                dot.edge("NUC:s", "AUX:n", weight="1", constraint="false")

                nuc_level_order.append("AUX")

                if layer_nuc["pre"]:
                    last_pre_nuc = layer_nuc["pre"][-1]
                    dot.edge(last_pre_nuc, "AUX", style="invis", weight="5")

                if cop_pos:
                    dot.node("AuxP", cop_pos, shape="plaintext", fontsize="10", group="aux_group")
                    dot.edge("AUX:s", "AuxP:n", weight="100")
                    dot.edge("AuxP:s", "AuxW:n", weight="100")
                else:
                    dot.edge("AUX:s", "AuxW:n", weight="100")

                terminal_words.append("AuxW")
                ordered_bottom.append("AuxW")

                reference_to_node["copula"] = "AuxW"
                nucleus_anchor = "AuxW"  # temporary; later fixed to AttrW

            # Items between AUX and PRED (attribute)
            if items_between:
                last_conn_type_between = None
                current_peri_parent_between = None

                for i, item in enumerate(items_between):
                    if not item.get("text"):
                        continue

                    uid = f"Between_{i}"
                    conn_type = item.get("conn_type")

                    if conn_type == "Arg":
                        last_conn_type_between = None
                        current_peri_parent_between = None

                        top_id = f"{uid}_Top"

                        if is_morph(item):
                            forced_lbl = "AFF" if is_affix_morph(item) else "CL"
                            dot.node(top_id, forced_lbl, shape="plaintext", group=uid)
                        else:
                            dot.node(top_id, item.get("label", "XP"), shape="plaintext", group=uid)

                        # Anchor for between-args
                        if is_clitic_morph(item):
                            parent_anchor = get_clitic_anchor_id()
                        elif is_morph(item):
                            parent_anchor = "COREw" if (has_nuc and has_morphological) else "CORE"
                        else:
                            parent_anchor = "CORE"

                        dot.edge(
                            f"{parent_anchor}:s",
                            f"{top_id}:n",
                            weight="1",
                            constraint="false" if is_morph(item) else "true",
                        )

                        # ordering only for syntactic args
                        if not is_morph(item):
                            nuc_level_order.append(top_id)

                        if is_morph(item):
                            morph_arg_top_nodes.append(top_id)

                        wid = draw_word_structure(top_id, item, uid)
                        terminal_words.append(wid)
                        ordered_bottom.append(wid)

                        row_node_to_word[top_id] = wid
                        reference_to_node[f"between_{i}"] = wid

                    else:
                        # periphery between
                        if conn_type == last_conn_type_between and current_peri_parent_between:
                            parent_id = current_peri_parent_between
                            uid_for_group = f"Between_{i}"
                        else:
                            parent_id = f"PERI_Between_{uid}"
                            dot.node(parent_id, "PERIPHERY", shape="plaintext", group=uid)
                            uid_for_group = uid

                            if conn_type == "Peri-Clause":
                                target_layer_id = "CL"
                                layer_cl["pre"].append(parent_id)
                            elif conn_type == "Peri-Core":
                                target_layer_id = "CORE"
                                layer_core["pre"].append(parent_id)
                            else:
                                target_layer_id = "NUC"
                                layer_nuc["pre"].append(parent_id)

                            dot.edge(
                                f"{parent_id}:e",
                                f"{target_layer_id}:w",
                                arrowhead="vee",
                                constraint="false",
                                minlen="1",
                            )

                            last_conn_type_between = conn_type
                            current_peri_parent_between = parent_id

                        item_top_id = f"{uid}_Top"
                        dot.node(item_top_id, item.get("label", "XP"), shape="plaintext", group=uid_for_group)
                        dot.edge(f"{parent_id}:s", f"{item_top_id}:n", weight="100")

                        wid = draw_word_structure(item_top_id, item, uid_for_group)
                        terminal_words.append(wid)
                        ordered_bottom.append(wid)

                        if parent_id and parent_id not in row_node_to_word:
                            row_node_to_word[parent_id] = wid

                        reference_to_node[f"between_{i}"] = wid

            dot.node("PRED_A", "PRED", shape="plaintext", fontsize="10", group="main")
            dot.node("AttrW", attr_word, shape="none", group="main")
            dot.edge("NUC:s", "PRED_A:n", weight="100")
            nuc_level_order.append("PRED_A")

            if has_morphological:
                if attr_pos:
                    dot.node("AttrP", attr_pos, shape="plaintext", fontsize="10", group="main")
                    dot.edge("PRED_A:s", "AttrP:n", weight="100")
                    dot.edge("AttrP:s", "COREw:n", weight="100")
                    dot.edge("COREw:s", "NUCw:n", weight="100")
                    dot.edge("NUCw:s", "AttrW:n", weight="100")
                else:
                    dot.edge("PRED_A:s", "COREw:n", weight="100")
                    dot.edge("COREw:s", "NUCw:n", weight="100")
                    dot.edge("NUCw:s", "AttrW:n", weight="100")
            else:
                if attr_pos:
                    dot.node("AttrP", attr_pos, shape="plaintext", fontsize="10", group="main")
                    dot.edge("PRED_A:s", "AttrP:n", weight="100")
                    dot.edge("AttrP:s", "AttrW:n", weight="100")
                else:
                    dot.edge("PRED_A:s", "AttrW:n", weight="100")

            terminal_words.append("AttrW")
            ordered_bottom.append("AttrW")

            reference_to_node["attribute"] = "AttrW"
            nucleus_anchor = "AttrW"

            # align AUX / between-args / PRED
            if len(nuc_level_order) > 1:
                with dot.subgraph() as s:
                    s.attr(rank="same")
                    for node_id in nuc_level_order:
                        s.node(node_id)
                    for k in range(len(nuc_level_order) - 1):
                        s.edge(nuc_level_order[k], nuc_level_order[k + 1], style="invis", weight="10")
            elif cop_word:
                with dot.subgraph() as s:
                    s.attr(rank="same")
                    s.node("AUX")
                    s.node("PRED_A")

        # Post items
        process_item_group(items_post, "Post")

    else:
        process_item_group(items_pre, "Pre")
        process_item_group(items_post, "Post")

    # Post slots
    w_pocs = draw_slot("PoCS", pocs, "CL", layer_core["post"], "pocs")
    if w_pocs:
        ordered_bottom.append(w_pocs)

    w_podp = draw_slot("PoDP", podp, "S", layer_cl["post"], "podp")
    if w_podp:
        ordered_bottom.append(w_podp)

    # =========================
    # EXTRA-CORE SLOTS
    # =========================
    def _side_relative_to_nuc(ref_code: str) -> str:
        if not nucleus_anchor or nucleus_anchor not in ordered_bottom:
            return "right"

        nuc_idx = ordered_bottom.index(nucleus_anchor)

        if not ref_code:
            return "right"

        ref_node = reference_to_node.get(ref_code)
        if not ref_node or ref_node not in ordered_bottom:
            return "right"

        ref_idx = ordered_bottom.index(ref_node)

        if ref_idx < nuc_idx:
            return "left"
        if ref_idx > nuc_idx:
            return "right"
        return "center"

    for i, slot in enumerate(extra_core_slots):
        if not slot or not slot.get("text"):
            continue

        uid = f"ExCS{i}"

        ref_code = (slot.get("reference") or "").strip()
        pos = (slot.get("position") or "right").strip().lower()

        ref_side = _side_relative_to_nuc(ref_code)

        if ref_side == "left":
            target_list = layer_core["pre"]
        elif ref_side == "right":
            target_list = layer_core["post"]
        else:
            target_list = layer_core["pre"] if pos == "left" else layer_core["post"]

        # IMPORTANT: do not allow the CL→ExCS edge to pull CL/CORE horizontally
        w_excs = draw_slot(
            uid,
            slot,
            parent="CL",
            target_list=target_list,
            ref_code=f"excs_{i}",
            show_uid_label=False,
            parent_edge_constraint=False,
        )
        if not w_excs:
            continue

        ref_node_id = reference_to_node.get(ref_code) if ref_code else None

        if ref_node_id and ref_node_id in ordered_bottom:
            ref_idx = ordered_bottom.index(ref_node_id)
            if pos == "left":
                ordered_bottom.insert(ref_idx, w_excs)
            else:
                ordered_bottom.insert(ref_idx + 1, w_excs)
        else:
            ordered_bottom.append(w_excs)

    # =========================
    # INSERT REALIZATION FORMS (after Extra-Core Slots)
    # =========================
    for idx, form in enumerate(realization_forms):
        form_text = (form.get("text", "") or "").strip()
        if not form_text:
            continue

        position = (form.get("position", "right") or "right").strip().lower()
        reference_code = (form.get("reference", "") or "").strip()

        ref_node_id = reference_to_node.get(reference_code)
        if not ref_node_id:
            continue

        form_node_id = f"REAL_{idx}"
        dot.node(form_node_id, form_text, shape="none", fontsize="11", group="real")
        terminal_words.append(form_node_id)
        reference_to_node[f"real_{idx}"] = form_node_id

        if ref_node_id in ordered_bottom:
            ref_index = ordered_bottom.index(ref_node_id)
            if position == "left":
                ordered_bottom.insert(ref_index, form_node_id)
            else:
                ordered_bottom.insert(ref_index + 1, form_node_id)
        else:
            ordered_bottom.append(form_node_id)

    # OPERATORS
    operators = data.get("operators", [])
    if operators and nucleus_anchor:
        draw_operator_projection(nucleus_anchor, operators, reference_to_node)

    # ==========================================================
    # ALIGNMENT FIX FINAL:
    # ==========================================================
    def _word_index(word_id: str) -> int:
        try:
            return ordered_bottom.index(word_id)
        except ValueError:
            return 10**9

    def _row_index(row_node_id: str) -> int:
        w = row_node_to_word.get(row_node_id)
        if w:
            return _word_index(w)
        return _word_index(row_node_id)

    anchor_idx = len(ordered_bottom) // 2
    if nucleus_anchor and nucleus_anchor in ordered_bottom:
        anchor_idx = ordered_bottom.index(nucleus_anchor)

    def _unique(seq):
        return list(dict.fromkeys(seq))

    def _build_row(layer_dict, spine_node: str):
        items = _unique(layer_dict.get("pre", []) + layer_dict.get("post", []))
        items = [n for n in items if n != spine_node]
        items_sorted = sorted(items, key=_row_index)
        left = [n for n in items_sorted if _row_index(n) < anchor_idx]
        right = [n for n in items_sorted if _row_index(n) >= anchor_idx]
        return left + ([spine_node] if spine_node else []) + right

    def enforce_rank(row_nodes):
        row_nodes = [n for n in row_nodes if n]
        if not row_nodes:
            return
        with dot.subgraph() as s:
            s.attr(rank="same")
            for n in row_nodes:
                s.node(n)
            for i in range(1, len(row_nodes)):
                s.edge(row_nodes[i - 1], row_nodes[i], style="invis", weight="100")

    enforce_rank(_build_row(layer_cl, "CL"))
    enforce_rank(_build_row(layer_core, "CORE"))

    if has_nuc:
        enforce_rank(_build_row(layer_nuc, "NUC"))

    # Align morph arg tops (AFF/CL) with NUCw,
    # placing pre-nuclear morphs to the LEFT of NUCw and post-nuclear morphs to the RIGHT.
    if has_nuc and has_morphological and morph_arg_top_nodes:
        morph_unique = _unique(morph_arg_top_nodes)

        # anchor_idx already computed above (nucleus position in ordered_bottom)
        left_morph = [n for n in morph_unique if _row_index(n) < anchor_idx]
        right_morph = [n for n in morph_unique if _row_index(n) >= anchor_idx]

        left_sorted = sorted(left_morph, key=_row_index)
        right_sorted = sorted(right_morph, key=_row_index)

        with dot.subgraph() as s:
            s.attr(rank="same")

            for n in left_sorted:
                s.node(n)

            s.node("NUCw")

            for n in right_sorted:
                s.node(n)

            # keep order among left morphs
            for i in range(1, len(left_sorted)):
                s.edge(left_sorted[i - 1], left_sorted[i], style="invis", weight="100")

            # left morphs must end before NUCw
            if left_sorted:
                s.edge(left_sorted[-1], "NUCw", style="invis", weight="80", minlen="2")

            # NUCw must come before right morphs
            if right_sorted:
                s.edge("NUCw", right_sorted[0], style="invis", weight="80", minlen="2")

            # keep order among right morphs
            for i in range(1, len(right_sorted)):
                s.edge(right_sorted[i - 1], right_sorted[i], style="invis", weight="100")

    # All words same horizontal baseline
    if terminal_words:
        with dot.subgraph() as s:
            s.attr(rank="same")
            for n in terminal_words:
                s.node(n)

    # Keep linear order at bottom (this is the main order constraint)
    for i in range(len(ordered_bottom) - 1):
        dot.edge(ordered_bottom[i], ordered_bottom[i + 1], style="invis", weight="10")

    return dot, pending_op_connections, reference_to_node


def postprocess_svg_with_connections(svg_code, connections, ref_to_node):
    import xml.etree.ElementTree as ET

    if not connections:
        return svg_code, 0, 0

    ET.register_namespace("", "http://www.w3.org/2000/svg")
    ET.register_namespace("xlink", "http://www.w3.org/1999/xlink")

    try:
        root = ET.fromstring(svg_code)
    except ET.ParseError:
        return svg_code, 0, 0

    def find_node_bbox(node_id):
        for g in root.findall(".//{http://www.w3.org/2000/svg}g[@class='node']"):
            title = g.find("{http://www.w3.org/2000/svg}title")
            if title is not None and title.text == node_id:
                text_elem = g.find("{http://www.w3.org/2000/svg}text")
                if text_elem is not None:
                    x = float(text_elem.get("x", 0))
                    y = float(text_elem.get("y", 0))
                    text_content = text_elem.text or ""
                    width = len(text_content) * 7
                    height = 14
                    return {
                        "x": x,
                        "y": y,
                        "width": width,
                        "height": height,
                        "cx": x,
                        "cy": y - height * 0.35,
                    }
        return None

    graph_g = root.find(".//{http://www.w3.org/2000/svg}g[@class='graph']")
    if graph_g is None:
        graph_g = root.find(".//{http://www.w3.org/2000/svg}g")
    if graph_g is None:
        return svg_code, 0, 0

    vb = root.get("viewBox")
    original_min_x = 0
    original_max_x = 0
    if vb:
        parts = vb.strip().split()
        if len(parts) == 4:
            vb_x, vb_y, vb_w, vb_h = map(float, parts)
            original_min_x = vb_x
            original_max_x = vb_x + vb_w

    min_x_used = original_min_x
    max_x_used = original_max_x

    for conn in connections:
        lbl_id = conn["lbl_id"]
        target_ids = conn.get("target_node_ids", [])
        side = conn["side"]
        layer = conn.get("layer", "NUC")

        if not target_ids:
            continue

        lbl_bbox = find_node_bbox(lbl_id)
        if lbl_bbox is None:
            continue

        target_bboxes = []
        for tid in target_ids:
            bbox = find_node_bbox(tid)
            if bbox:
                target_bboxes.append(bbox)
        if not target_bboxes:
            continue

        if side == "Left":
            p1_x = lbl_bbox["cx"] - lbl_bbox["width"] / 2 - 2
        else:
            p1_x = lbl_bbox["cx"] + lbl_bbox["width"] / 2 + 2
        p1_y = lbl_bbox["cy"]

        if layer == "CLAUSE":
            distance = 10
        elif layer == "CORE":
            distance = 8
        else:
            distance = 5

        if side == "Left":
            p2_x = p1_x - distance
        else:
            p2_x = p1_x + distance
        p2_y = p1_y

        p3_x = p2_x
        avg_target_y = sum(tb["cy"] for tb in target_bboxes) / len(target_bboxes)
        p3_y = p2_y - distance if avg_target_y < p2_y else p2_y + distance

        trunk_d = f"M {p1_x},{p1_y} L {p2_x},{p2_y} L {p3_x},{p3_y}"
        trunk_elem = ET.SubElement(graph_g, "{http://www.w3.org/2000/svg}path")
        trunk_elem.set("d", trunk_d)
        trunk_elem.set("stroke", "black")
        trunk_elem.set("stroke-width", "0.8")
        trunk_elem.set("stroke-dasharray", "5,3")
        trunk_elem.set("fill", "none")

        min_x_used = min(min_x_used, p1_x, p2_x, p3_x)
        max_x_used = max(max_x_used, p1_x, p2_x, p3_x)

        for tb in target_bboxes:
            # separación extra para que la línea no "toque" visualmente las letras
            offset = (tb.get("height", 14) * 0.25) + 8  # ajusta el 6 si quieres más/menos aire

            p4_x = tb["cx"]
            p4_y = tb["cy"] + offset if tb["cy"] < p3_y else tb["cy"] - offset

            branch_d = f"M {p3_x},{p3_y} L {p4_x},{p4_y}"
            branch_elem = ET.SubElement(graph_g, "{http://www.w3.org/2000/svg}path")
            branch_elem.set("d", branch_d)
            branch_elem.set("stroke", "black")
            branch_elem.set("stroke-width", "0.8")
            branch_elem.set("stroke-dasharray", "5,3")
            branch_elem.set("fill", "none")

            min_x_used = min(min_x_used, p4_x)
            max_x_used = max(max_x_used, p4_x)

    extra_left = max(0, original_min_x - min_x_used + 20)
    extra_right = max(0, max_x_used - original_max_x + 20)

    return ET.tostring(root, encoding="unicode"), extra_left, extra_right


def expand_svg_viewbox(svg_code, pad_left=0, pad_right=0, pad_top=0, pad_bottom=0):
    import xml.etree.ElementTree as ET

    NS = "http://www.w3.org/2000/svg"
    ET.register_namespace("", NS)

    try:
        root = ET.fromstring(svg_code)
    except ET.ParseError:
        return svg_code

    vb = root.get("viewBox")
    if not vb:
        return svg_code

    parts = vb.strip().split()
    if len(parts) != 4:
        return svg_code

    x, y, w, h = map(float, parts)

    new_x = x - pad_left
    new_y = y - pad_top
    new_w = w + pad_left + pad_right
    new_h = h + pad_top + pad_bottom

    root.set("viewBox", f"{new_x:.2f} {new_y:.2f} {new_w:.2f} {new_h:.2f}")

    w_attr = root.get("width")
    h_attr = root.get("height")

    if w_attr:
        m = re.match(r"^\s*([0-9.]+)", w_attr)
        if m:
            wn = float(m.group(1))
            root.set("width", f"{wn + pad_left + pad_right:.2f}pt")
    if h_attr:
        m = re.match(r"^\s*([0-9.]+)", h_attr)
        if m:
            hn = float(m.group(1))
            root.set("height", f"{hn + pad_top + pad_bottom:.2f}pt")

    return ET.tostring(root, encoding="unicode")


# ==========================================
# INTERFACE
# ==========================================
try:
    logo_path = Path(__file__).parent / "albura_logo.png"
    with open(logo_path, "rb") as f:
        logo_data = base64.b64encode(f.read()).decode()
    st.markdown(
        f'<img src="data:image/png;base64,{logo_data}" alt="Albura" width="300">',
        unsafe_allow_html=True,
    )
except Exception:
    st.title("Albura")

st.caption("An assistant for diagramming the Layered Structure of the Clause (LSC) in Role and Reference Grammar")
st.markdown("---")

main_c1, main_c2 = st.columns([1, 3])

p_type_key = "verbal"

with main_c1:
    st.subheader("Constituents")

    # -------------------------
    # 1) NUCLEUS
    # -------------------------
    with st.expander("1. Nucleus", expanded=False):
        pred_type = st.radio(
            "Type", 
            ["Predicative", "Attributive"], 
            horizontal=True, 
            key=get_key("pred_type"),
            help="Predicative: Verbal predicates. Attributive: Copular constructions (AUX + PRED)."
        )

        nucleus_data = {"text": "", "pos": ""}
        copula_data = {"text": "", "pos": ""}
        attribute_data = {"text": "", "pos": ""}
        items_between_data = []

        if pred_type == "Predicative":
            c1, c2 = st.columns([2, 1])
            nucleus_data["text"] = c1.text_input("Data", key=get_key("nuc_txt"))
            nucleus_data["pos"] = c2.text_input("PoS", key=get_key("nuc_pos"), help="Optional Part of Speech or category tag (e.g., N, P, Adv). It will be rendered between the node label and the word.")
            p_type_key = "verbal"
        else:
            st.markdown("**AUX**")
            c1, c2 = st.columns([2, 1])
            copula_data["text"] = c1.text_input("Data", key=get_key("aux_txt"))
            copula_data["pos"] = c2.text_input("PoS", key=get_key("aux_pos"), help="Optional Part of Speech or category tag (e.g., N, P, Adv). It will be rendered between the node label and the word.")

            st.markdown("**PRED**")
            c3, c4 = st.columns([2, 1])
            attribute_data["text"] = c3.text_input("Data", key=get_key("attr_txt"))
            attribute_data["pos"] = c4.text_input("PoS", key=get_key("attr_pos"), help="Optional Part of Speech or category tag (e.g., N, P, Adv). It will be rendered between the node label and the word.")

            st.markdown("---")
            st.markdown("**Constituents between AUX and PRED**")
            st.caption("(from leftmost to rightmost)")
            num_between = st.number_input(
                "Number of items", 
                min_value=0, 
                value=0, 
                key=get_key("num_between"),
                help="Use this for arguments or adjuncts located between the copula and the attribute (e.g., 'is **she often** happy?')."
)

            if num_between > 0:
                conn_map = {
                    "Argument": ("Arg", "XP"),
                    "Periphery (NUC)": ("Peri-Nuc", "XP"),
                    "Periphery (CORE)": ("Peri-Core", "XP"),
                    "Periphery (CLAUSE)": ("Peri-Clause", "XP"),
                }

                for i in range(num_between):
                    st.markdown(f"**Item {i+1}**")
                    conn_type_raw = st.selectbox("Type", list(conn_map.keys()), key=get_key(f"betw_c_{i}"))
                    code, def_lbl = conn_map[conn_type_raw]

                    arg_type = None
                    if conn_type_raw == "Argument":
                        arg_type = st.radio(
                            "Argument type",
                            ["Syntactic", "Morphological"],
                            horizontal=True,
                            key=get_key(f"betw_argtype_{i}"),
                            help="Syntactic: Standard phrasal arguments (RP, PP). Morphological: Affixes or clitics attached to the COREw/NUCw nodes."
                        )

                    c1, c2, c3 = st.columns([2, 1, 1])

                    txt = c1.text_input("Data", key=get_key(f"betw_t_{i}"))

                    morph_form = None
                    if conn_type_raw == "Argument" and arg_type == "Morphological":
                        morph_form = c2.selectbox(
                            "Label",
                            ["Affix", "Clitic"],
                            key=get_key(f"betw_morphform_{i}")
                        )
                        lbl = "AFF" if morph_form == "Affix" else "CL"
                    else:
                        lbl = c2.text_input("Label", value=def_lbl, key=get_key(f"betw_l_{i}"))

                    pos = c3.text_input("PoS", key=get_key(f"betw_p_{i}"), help="Optional Part of Speech or category tag (e.g., N, P, Adv). It will be rendered between the node label and the word.")

                    items_between_data.append({
                        "label": lbl,
                        "text": txt,
                        "pos": pos,
                        "conn_type": code,
                        "arg_type": arg_type,
                        "morph_form": morph_form
                    })

            p_type_key = "copular"

    # -------------------------
    # 2) ARGUMENTS / ADJUNCTS
    # -------------------------
    with st.expander("2. Arguments and adjuncts", expanded=False):
        st.caption("(from leftmost to rightmost)")

        conn_map = {
            "Argument": ("Arg", "XP"),
            "Periphery (NUC)": ("Peri-Nuc", "XP"),
            "Periphery (CORE)": ("Peri-Core", "XP"),
            "Periphery (CLAUSE)": ("Peri-Clause", "XP"),
        }

        st.caption("**Pre-nuclear**")
        num_pre = st.number_input("Number of items", min_value=0, value=0, key=get_key("num_pre"))

        items_pre_data = []
        for i in range(num_pre):
            st.markdown(f"**Item {i+1}**")
            conn_type_raw = st.selectbox("Type", list(conn_map.keys()), key=get_key(f"pre_c_{i}"))
            code, def_lbl = conn_map[conn_type_raw]

            arg_type = None
            if conn_type_raw == "Argument":
                arg_type = st.radio(
                    "Argument type",
                    ["Syntactic", "Morphological"],
                    horizontal=True,
                    key=get_key(f"pre_argtype_{i}"),
                    help="Syntactic: Standard phrasal arguments (RP, PP). Morphological: Affixes or clitics attached to the COREw/NUCw nodes."
                )

            c1, c2, c3 = st.columns([2, 1, 1])

            txt = c1.text_input("Data", key=get_key(f"pre_t_{i}"))

            morph_form = None
            if conn_type_raw == "Argument" and arg_type == "Morphological":
                morph_form = c2.selectbox(
                    "Label",
                    ["Affix", "Clitic"],
                    key=get_key(f"pre_morphform_{i}")
                )
                lbl = "AFF" if morph_form == "Affix" else "CL"
            else:
                lbl = c2.text_input("Label", value=def_lbl, key=get_key(f"pre_l_{i}_{code}"))

            pos = c3.text_input("PoS", key=get_key(f"pre_p_{i}"), help="Optional Part of Speech or category tag (e.g., N, P, Adv). It will be rendered between the node label and the word.")

            items_pre_data.append({
                "label": lbl,
                "text": txt,
                "pos": pos,
                "conn_type": code,
                "arg_type": arg_type,
                "morph_form": morph_form
            })

        st.markdown("---")

        st.caption("**Post-nuclear**")
        num_post = st.number_input("Number of items", min_value=0, value=0, key=get_key("num_post"))

        items_post_data = []
        for i in range(num_post):
            st.markdown(f"**Item {i+1}**")
            conn_type_raw = st.selectbox("Type", list(conn_map.keys()), key=get_key(f"post_c_{i}"))
            code, def_lbl = conn_map[conn_type_raw]

            arg_type = None
            if conn_type_raw == "Argument":
                arg_type = st.radio(
                    "Argument type",
                    ["Syntactic", "Morphological"],
                    horizontal=True,
                    key=get_key(f"post_argtype_{i}"),
                    help="Syntactic: Standard phrasal arguments (RP, PP). Morphological: Affixes or clitics attached to the COREw/NUCw nodes."
                )

            c1, c2, c3 = st.columns([2, 1, 1])

            txt = c1.text_input("Data", key=get_key(f"post_t_{i}"))

            morph_form = None
            if conn_type_raw == "Argument" and arg_type == "Morphological":
                morph_form = c2.selectbox(
                    "Label",
                    ["Affix", "Clitic"],
                    key=get_key(f"post_morphform_{i}")
                )
                lbl = "AFF" if morph_form == "Affix" else "CL"
            else:
                lbl = c2.text_input("Label", value=def_lbl, key=get_key(f"post_l_{i}_{code}"))

            pos = c3.text_input("PoS", key=get_key(f"post_p_{i}"), help="Optional Part of Speech or category tag (e.g., N, P, Adv). It will be rendered between the node label and the word.")

            items_post_data.append({
                "label": lbl,
                "text": txt,
                "pos": pos,
                "conn_type": code,
                "arg_type": arg_type,
                "morph_form": morph_form
            })

    # -------------------------
    # 3) TOPICS / FOCI
    # -------------------------
    with st.expander("3. Topics and foci", expanded=False):
        def input_peri(label_ui, key_prefix, default_lbl="XP"):
            st.markdown(f"**{label_ui}**")
            c1, c2, c3 = st.columns([2, 1, 1])
            txt = c1.text_input("Data", key=get_key(f"{key_prefix}_txt"))
            lbl = c2.text_input("Label", default_lbl, key=get_key(f"{key_prefix}_lbl"))
            pos = c3.text_input("PoS", key=get_key(f"{key_prefix}_pos"), help="Optional Part of Speech or category tag (e.g., N, P, Adv). It will be rendered between the node label and the word.")
            return {"label": lbl, "text": txt, "pos": pos}

        prdp = input_peri("PrDP", "prdp", "XP")
        podp = input_peri("PoDP", "podp", "XP")
        st.markdown("---")
        prcs = input_peri("PrCS", "prcs", "XP")
        pocs = input_peri("PoCS", "pocs", "XP")

    # -------------------------
    # 4) EXTRA-CORE SLOTS
    # -------------------------
    with st.expander("4. Extra-Core Slots", expanded=False):
        st.caption("(drawn as CORE-level slots attached to CL)")

        num_excs = st.number_input("Number of items", min_value=0, value=0, key=get_key("num_excs"))

        extra_core_slots_data = []
        base_reference_items = []

        if pred_type == "Predicative" and nucleus_data.get("text"):
            base_reference_items.append(("Nucleus", "nucleus"))
        elif pred_type == "Attributive":
            if copula_data.get("text"):
                base_reference_items.append(("Copula (AUX)", "copula"))
            if attribute_data.get("text"):
                base_reference_items.append(("Attribute (PRED)", "attribute"))

        for i, item in enumerate(items_pre_data):
            if item.get("text"):
                base_reference_items.append((f"Pre-nuclear {i+1}: {item.get('text','')[:20]}", f"pre_{i}"))

        for i, item in enumerate(items_between_data):
            if item.get("text"):
                base_reference_items.append((f"Between {i+1}: {item.get('text','')[:20]}", f"between_{i}"))

        for i, item in enumerate(items_post_data):
            if item.get("text"):
                base_reference_items.append((f"Post-nuclear {i+1}: {item.get('text','')[:20]}", f"post_{i}"))

        if prdp.get("text"):
            base_reference_items.append(("PrDP", "prdp"))
        if prcs.get("text"):
            base_reference_items.append(("PrCS", "prcs"))
        if pocs.get("text"):
            base_reference_items.append(("PoCS", "pocs"))
        if podp.get("text"):
            base_reference_items.append(("PoDP", "podp"))

        for i in range(num_excs):
            st.markdown(f"**Item {i+1}**")

            c1, c2, c3 = st.columns([2, 1, 1])
            txt = c1.text_input("Data", key=get_key(f"excs_t_{i}"))
            lbl = c2.text_input("Label", value="XP", key=get_key(f"excs_l_{i}"))
            pos = c3.text_input("PoS", key=get_key(f"excs_p_{i}"), help="Optional Part of Speech or category tag (e.g., N, P, Adv). It will be rendered between the node label and the word.")

            c4, c5 = st.columns([1, 1])
            position = c4.selectbox(
                "Position", 
                ["Left of", "Right of"], 
                key=get_key(f"excs_pos_{i}"),
                help="Determines the linear order of the Extra-Core Slot relative to the reference item selected."
            )

            current_refs = base_reference_items.copy()
            for j in range(i):
                prev_txt = extra_core_slots_data[j].get("text", "")
                if prev_txt:
                    current_refs.append((f"Extra-Core {j+1}: {prev_txt[:20]}", f"excs_{j}"))

            if current_refs:
                ref_labels = [x[0] for x in current_refs]
                ref_choice = c5.selectbox(
                    "Reference item", 
                    ref_labels, 
                    key=get_key(f"excs_ref_{i}"),
                    help="Select the existing constituent that will serve as the anchor for positioning this slot."
                )
                ref_code = current_refs[ref_labels.index(ref_choice)][1]
            else:
                ref_code = None

            extra_core_slots_data.append(
                {
                    "label": lbl,
                    "text": txt,
                    "pos": pos,
                    "position": "left" if position == "Left of" else "right",
                    "reference": ref_code,
                }
            )

    # -------------------------
    # 5) OPERATORS
    # -------------------------
    st.subheader("Operators")

    # Realization Forms
    with st.expander("Realization forms", expanded=False):
        st.caption("If operators are expressed in items not present in the constituent projection, enter them here.")

        num_realizations = st.number_input("Number of items", min_value=0, value=0, key=get_key("num_realizations"))

        realization_forms_data = []

        if num_realizations > 0:
            reference_items = []

            if pred_type == "Predicative" and nucleus_data.get("text"):
                reference_items.append(("Nucleus", "nucleus"))
            elif pred_type == "Attributive":
                if copula_data.get("text"):
                    reference_items.append(("Copula (AUX)", "copula"))
                if attribute_data.get("text"):
                    reference_items.append(("Attribute (PRED)", "attribute"))

            for i, item in enumerate(items_pre_data):
                if item.get("text"):
                    reference_items.append((f"Pre-nuclear {i+1}: {item.get('text','')[:20]}", f"pre_{i}"))

            for i, item in enumerate(items_between_data):
                if item.get("text"):
                    reference_items.append((f"Between {i+1}: {item.get('text','')[:20]}", f"between_{i}"))

            for i, item in enumerate(items_post_data):
                if item.get("text"):
                    reference_items.append((f"Post-nuclear {i+1}: {item.get('text','')[:20]}", f"post_{i}"))

            if prdp.get("text"):
                reference_items.append(("PrDP", "prdp"))
            if prcs.get("text"):
                reference_items.append(("PrCS", "prcs"))
            if pocs.get("text"):
                reference_items.append(("PoCS", "pocs"))
            if podp.get("text"):
                reference_items.append(("PoDP", "podp"))

            for i, slot in enumerate(extra_core_slots_data):
                if slot.get("text"):
                    reference_items.append((f"Extra-Core {i+1}: {slot['text'][:20]}", f"excs_{i}"))

            for i in range(num_realizations):
                st.markdown(f"**Realization form {i+1}**")

                c1, c2 = st.columns([1, 1])

                form_text = c1.text_input(
                    "Form",
                    key=get_key(f"real_text_{i}"),
                    help="Any item other than an argument or adjunct that serves as realization of an operator, such as affixes or particles (e.g., -able, will, Ø, -ing)",
                )

                position = c2.selectbox("Position", ["Left of", "Right of"], key=get_key(f"real_pos_{i}"))

                current_references = reference_items.copy()
                for j in range(i):
                    prev_form = st.session_state.get(get_key(f"real_text_{j}"), "")
                    if prev_form:
                        current_references.append((f"Realization {j+1}: {prev_form}", f"real_{j}"))

                if current_references:
                    reference_labels = [item[0] for item in current_references]
                    reference = st.selectbox("Reference item", reference_labels, key=get_key(f"real_ref_{i}"))

                    selected_idx = reference_labels.index(reference)
                    reference_code = current_references[selected_idx][1]

                    realization_forms_data.append(
                        {"text": form_text, "position": "left" if position == "Left of" else "right", "reference": reference_code}
                    )
                else:
                    st.warning("No reference items available. Please add constituents first.")
                    break

    # Operators by layer
    ops_nuc = ["Aspect", "Negation", "Directionals"]
    ops_core = ["Directionals", "Event quantification", "Modality", "Negation"]
    ops_clause = ["Status", "Negation", "Tense", "Evidentiality", "Illocutionary force"]

    operators_data = []

    def operator_box(title, layer_code, ops_list, key_prefix, realization_forms):
        with st.expander(title, expanded=False):
            n = st.number_input("Number of operators", min_value=0, value=0, key=get_key(f"{key_prefix}_n"))

            for i in range(n):
                st.markdown(f"**Operator {i+1}**")

                op_type = st.selectbox("Type", options=ops_list, key=get_key(f"{key_prefix}_type_{i}"))

                c1, c2 = st.columns([1, 1])

                op_value = c1.text_input(
                    "Value", 
                    key=get_key(f"{key_prefix}_value_{i}"),
                    help="The grammatical value of the operator (e.g., 'PAST', 'PROGR', 'DECL')."
                )

                label_side = c2.selectbox(
                    "Label position", 
                    options=["Right", "Left"], 
                    index=0, 
                    key=get_key(f"{key_prefix}_side_{i}"),
                    help="Determines if the operator label appears on the left or right side of the projection spine."
                )

                target_options = [("None", None)]

                if pred_type == "Predicative" and nucleus_data.get("text"):
                    target_options.append((f"Nucleus: {nucleus_data['text']}", "nucleus"))
                elif pred_type == "Attributive":
                    if copula_data.get("text"):
                        target_options.append((f"Copula: {copula_data['text']}", "copula"))
                    if attribute_data.get("text"):
                        target_options.append((f"Attribute: {attribute_data['text']}", "attribute"))

                for idx, item in enumerate(items_pre_data):
                    if item.get("text"):
                        target_options.append((f"Pre-nuclear {idx+1}: {item['text'][:20]}", f"pre_{idx}"))

                for idx, item in enumerate(items_between_data):
                    if item.get("text"):
                        target_options.append((f"Between {idx+1}: {item['text'][:20]}", f"between_{idx}"))

                for idx, item in enumerate(items_post_data):
                    if item.get("text"):
                        target_options.append((f"Post-nuclear {idx+1}: {item['text'][:20]}", f"post_{idx}"))

                if prdp.get("text"):
                    target_options.append((f"PrDP: {prdp['text'][:20]}", "prdp"))
                if prcs.get("text"):
                    target_options.append((f"PrCS: {prcs['text'][:20]}", "prcs"))
                if pocs.get("text"):
                    target_options.append((f"PoCS: {pocs['text'][:20]}", "pocs"))
                if podp.get("text"):
                    target_options.append((f"PoDP: {podp['text'][:20]}", "podp"))

                for idx, slot in enumerate(extra_core_slots_data):
                    if slot.get("text"):
                        target_options.append((f"Extra-Core {idx+1}: {slot['text'][:20]}", f"excs_{idx}"))

                for idx, form in enumerate(realization_forms):
                    if form.get("text"):
                        target_options.append((f"Realization form {idx+1}: {form['text']}", f"real_{idx}"))

                target_labels = [opt[0] for opt in target_options]
                targets = st.multiselect(
                    "Links to",
                    options=target_labels[1:],
                    key=get_key(f"{key_prefix}_target_{i}"),
                    help="Select the constituent(s) or realization form(s) this operator links to. They can be more than one. This will draw the dashed connection lines.",
                )

                target_codes = []
                for t in targets:
                    idx = target_labels.index(t)
                    target_codes.append(target_options[idx][1])

                operators_data.append({"operator": op_type, "value": op_value, "layer": layer_code, "side": label_side, "targets": target_codes})

    operator_box("Nucleus", "NUC", ops_nuc, "op_nuc", realization_forms_data)
    operator_box("Core", "CORE", ops_core, "op_core", realization_forms_data)
    operator_box("Clause", "CLAUSE", ops_clause, "op_clause", realization_forms_data)

    st.markdown("---")

    h1, h2 = st.columns([0.9, 0.1])
    with h1:
        st.page_link("pages/01_User_Manual.py", label="User Manual", icon="📘")

    st.markdown("---")
    st.caption("by Carlos González Vergara (__cgonzalv@uc.cl__)")

    try:
        cc_icon_path = Path(__file__).parent / "cc_icon.png"
        with open(cc_icon_path, "rb") as f:
            img_data = base64.b64encode(f.read()).decode()
        st.markdown(
            f'<a href="https://creativecommons.org/licenses/by-nc-nd/4.0/" target="_blank">'
            f'<img src="data:image/png;base64,{img_data}" alt="CC BY-NC-ND 4.0" width="88"></a>',
            unsafe_allow_html=True,
        )
    except Exception:
        st.markdown("[CC BY 4.0](https://creativecommons.org/licenses/by-nc-nd/4.0/)")


# ==========================================
# RIGHT PANEL (OUTPUT)
# ==========================================
with main_c2:
    show_graph = False
    if p_type_key == "verbal" and nucleus_data["text"]:
        show_graph = True
    elif p_type_key == "copular" and attribute_data["text"]:
        show_graph = True

    if show_graph:
        data = {
            "prdp": prdp,
            "prcs": prcs,
            "pred_type": p_type_key,
            "nucleus": nucleus_data,
            "copula": copula_data,
            "attribute": attribute_data,
            "items_between": items_between_data,
            "items_pre": items_pre_data,
            "items_post": items_post_data,
            "pocs": pocs,
            "podp": podp,
            "operators": operators_data,
            "realization_forms": realization_forms_data,
            "extra_core_slots": extra_core_slots_data,
        }

        graph, pending_connections, node_mapping = draw_lsc_tree(data)

        btn_col1, btn_col2, btn_col3 = st.columns([0.12, 0.76, 0.12])
        with btn_col3:
            st.button(
                "New",
                width="stretch",
                on_click=reset_state,
                help="Generate new diagram",
            )

        try:
            graph.attr(dpi="72")
            svg_code = graph.pipe(format="svg").decode("utf-8")

            svg_code, extra_left, extra_right = postprocess_svg_with_connections(svg_code, pending_connections, node_mapping)

            svg_code = expand_svg_viewbox(
                svg_code,
                pad_left=max(10, extra_left),
                pad_right=max(10, extra_right),
                pad_top=10,
                pad_bottom=10
            )

            png_data = None
            try:
                import cairosvg
                png_data = cairosvg.svg2png(bytestring=svg_code.encode("utf-8"), dpi=300)
            except ImportError:
                pass

            with btn_col1:
                if png_data:
                    st.download_button(
                        "Download",
                        png_data,
                        "albura_tree.png",
                        "image/png",
                        width="stretch",
                    )
                else:
                    st.download_button(
                        "Download",
                        svg_code,
                        "albura_tree.svg",
                        "image/svg+xml",
                        width="stretch",
                    )

            svg_view = re.sub(r'(width|height)="[^"]*"', "", svg_code)

            html_content = f"""
            <div style="border: 1px solid #e0e0e0; border-radius: 8px;
                        padding: 10px; background-color: white;
                        box-sizing: border-box;">
                <div style="width: 100%; height: 700px; overflow: auto;
                            display: flex; justify-content: center;
                            align-items: flex-start; padding-top: 20px;">
                    <style>
                        svg {{
                            height: auto;
                            max-height: 700px;
                        }}
                        text {{
                            font-family: Helvetica, Arial, sans-serif !important;
                        }}
                    </style>
                    {svg_view}
                </div>
            </div>
            """
            components.html(html_content, height=780, scrolling=False)

        except Exception as e:
            st.error(f"Technical error: {e}")

    else:
        st.info("Fill in the data to begin")