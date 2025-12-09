import streamlit as st
import graphviz
import streamlit.components.v1 as components
import re

st.set_page_config(page_title="Albura - RRG tree diagram assistant", layout="wide")

# --- GESTIÓN DE ESTADO (Para que el botón New limpie de verdad) ---
if 'form_id' not in st.session_state:
    st.session_state['form_id'] = 0

def reset_state():
    st.session_state['form_id'] += 1

def get_key(base_name):
    return f"{base_name}_{st.session_state['form_id']}"

# --- DRAWING FUNCTION ---
def draw_lsc_tree(data):
    # Retrieve data
    prdp = data.get('prdp')
    prcs = data.get('prcs')
    items_pre = data.get('items_pre', [])
    items_post = data.get('items_post', [])
    pocs = data.get('pocs')
    podp = data.get('podp')
    
    pred_type = data.get('pred_type', 'verbal')
    nucleus = data.get('nucleus', {})
    nuc_word = nucleus.get('text', '')
    nuc_pos = nucleus.get('pos', '')
    
    copula = data.get('copula', {})
    cop_word = copula.get('text', '')
    cop_pos = copula.get('pos', '')
    
    attribute = data.get('attribute', {})
    attr_word = attribute.get('text', '')
    attr_pos = attribute.get('pos', '')
    
    items_between = data.get('items_between', [])

    dot = graphviz.Digraph(comment='LSC')
    
    # GRAPHIC SETTINGS
    # DPI 72 es estándar para web y evita que se generen coordenadas gigantes
    dot.attr(dpi='72') 
    dot.attr(splines='line', nodesep='0.4', ranksep='0.5', margin='0') 
    dot.attr('node', fontname='Helvetica', fontsize='11', height='0.2', width='0.2')
    dot.attr('edge', fontname='Helvetica', arrowhead='none', penwidth='0.8')
    
    # ALIGNMENT LISTS
    layer_cl = {'pre': [], 'center': ['CL'], 'post': []}
    layer_core = {'pre': [], 'center': ['CORE'], 'post': []}
    layer_nuc = {'pre': [], 'center': [], 'post': []} 
    
    terminal_words = []
    ordered_bottom = []

    # 1. SPINE STRUCTURE
    dot.node('S', 'SENTENCE', shape='plaintext', fontname="Helvetica", group='main')
    dot.node('CL', 'CLAUSE', shape='plaintext', fontname="Helvetica", group='main')
    dot.node('CORE', 'CORE', shape='plaintext', fontname="Helvetica", group='main')
    
    dot.edge('S:s', 'CL:n', weight='100')
    dot.edge('CL:s', 'CORE:n', weight='100')
    
    # 2. HELPER: DRAW WORDS
    def draw_word_structure(parent_id, item, uid):
        word_id = f"{uid}_W"
        dot.node(word_id, item['text'], shape='none', group=uid)
        if item['pos']:
            pos_id = f"{uid}_P"
            dot.node(pos_id, item['pos'], shape='plaintext', fontsize='10', group=uid)
            dot.edge(f'{parent_id}:s', f'{pos_id}:n', weight='100')
            dot.edge(f'{pos_id}:s', f'{word_id}:n', weight='100')
        else:
            dot.edge(f'{parent_id}:s', f'{word_id}:n', weight='100')
        return word_id

    # 3. HELPER: DRAW SLOTS
    def draw_slot(uid, data_dict, parent, target_list):
        if not data_dict or not data_dict.get('text'): return None
        dot.node(uid, uid, shape='plaintext', group=uid)
        dot.edge(f'{parent}:s', f'{uid}:n', weight='1')
        
        lbl_id = f'{uid}_L'
        dot.node(lbl_id, data_dict.get('label', 'XP'), shape='plaintext', group=uid)
        dot.edge(f'{uid}:s', f'{lbl_id}:n', weight='100')
        
        w_id = f'{uid}_W'
        dot.node(w_id, data_dict['text'], shape='none', group=uid)
        
        if data_dict.get('pos'):
            pos_id = f'{uid}_P'
            dot.node(pos_id, data_dict['pos'], shape='plaintext', fontsize='10', group=uid)
            dot.edge(f'{lbl_id}:s', f'{pos_id}:n', weight='100')
            dot.edge(f'{pos_id}:s', f'{w_id}:n', weight='100')
        else:
            dot.edge(f'{lbl_id}:s', f'{w_id}:n', weight='100')
            
        terminal_words.append(w_id)
        if target_list is not None: target_list.append(uid)
        return w_id

    # 4. HELPER: PROCESS ITEMS
    def process_item_group(items, side_prefix):
        last_conn_type = None
        current_peri_parent = None
        
        for i, item in enumerate(items):
            if not item['text']: continue
            uid = f"{side_prefix}_{i}"
            conn_type = item['conn_type']
            
            if conn_type == 'Arg':
                last_conn_type = None; current_peri_parent = None
                top_id = f"{uid}_Top"
                dot.node(top_id, item['label'], shape='plaintext', group=uid)
                dot.edge('CORE:s', f'{top_id}:n', weight='1')
                
                if side_prefix == 'Pre': layer_nuc['pre'].append(top_id)
                else: layer_nuc['post'].append(top_id)
                
                wid = draw_word_structure(top_id, item, uid)
                terminal_words.append(wid); ordered_bottom.append(wid)
            
            else: # Periphery
                if conn_type == last_conn_type and current_peri_parent:
                    parent_id = current_peri_parent
                    uid_for_group = f"{side_prefix}_{i}"
                else:
                    parent_id = f"PERI_Group_{uid}"
                    dot.node(parent_id, "PERIPHERY", shape='plaintext', group=uid)
                    uid_for_group = uid
                    
                    target_layer_id = ''
                    if conn_type == 'Peri-Clause': 
                        target_layer_id = 'CL'
                        if side_prefix == 'Pre': layer_cl['pre'].append(parent_id)
                        else: layer_cl['post'].append(parent_id)
                    elif conn_type == 'Peri-Core': 
                        target_layer_id = 'CORE'
                        if side_prefix == 'Pre': layer_core['pre'].append(parent_id)
                        else: layer_core['post'].append(parent_id)
                    elif conn_type == 'Peri-Nuc': 
                        target_layer_id = 'NUC'
                        if side_prefix == 'Pre': layer_nuc['pre'].append(parent_id)
                        else: layer_nuc['post'].append(parent_id)
                    
                    src, tgt = (':e', ':w') if side_prefix == 'Pre' else (':w', ':e')
                    dot.edge(f'{parent_id}{src}', f'{target_layer_id}{tgt}', arrowhead='normal', constraint='false', minlen='1')
                    
                    last_conn_type = conn_type; current_peri_parent = parent_id

                item_top_id = f"{uid}_Top"
                dot.node(item_top_id, item['label'], shape='plaintext', group=uid_for_group)
                dot.edge(f'{parent_id}:s', f'{item_top_id}:n', weight='100')
                wid = draw_word_structure(item_top_id, item, uid_for_group)
                terminal_words.append(wid); ordered_bottom.append(wid)

    # DRAW SLOTS
    w_prdp = draw_slot('PrDP', prdp, 'S', layer_cl['pre'])
    if w_prdp: ordered_bottom.append(w_prdp)
    
    w_prcs = draw_slot('PrCS', prcs, 'CL', layer_core['pre'])
    if w_prcs: ordered_bottom.append(w_prcs)

    process_item_group(items_pre, 'Pre')

    # NUCLEUS AREA
    has_nuc = (pred_type == 'verbal' and nuc_word) or (pred_type == 'copular' and attr_word)
    if has_nuc:
        layer_nuc['center'].append('NUC')
        dot.node('NUC', 'NUC', shape='plaintext', group='main')
        dot.edge('CORE:s', 'NUC:n', weight='100') 
        
        if pred_type == 'verbal':
            dot.node('PRED', 'PRED', shape='plaintext', fontsize='10', group='pred_verbal')
            dot.node('NucW', nuc_word, shape='none', group='pred_verbal')
            dot.edge('NUC:s', 'PRED:n', weight='100')
            if nuc_pos:
                dot.node('NucP', nuc_pos, shape='plaintext', fontsize='10', group='pred_verbal')
                dot.edge('PRED:s', 'NucP:n', weight='100'); dot.edge('NucP:s', 'NucW:n', weight='100')
            else:
                dot.edge('PRED:s', 'NucW:n', weight='100')
            terminal_words.append('NucW'); ordered_bottom.append('NucW')
            
        elif pred_type == 'copular':
            nuc_level_order = []
            
            if cop_word:
                dot.node('AUX', 'AUX', shape='plaintext', fontsize='10', group='aux_group')
                dot.node('AuxW', cop_word, shape='none', group='aux_group')
                dot.edge('NUC:s', 'AUX:n', weight='1')
                nuc_level_order.append('AUX')
                if layer_nuc['pre']:
                    last_pre_nuc = layer_nuc['pre'][-1]
                    dot.edge(last_pre_nuc, 'AUX', style='invis', weight='5')
                if cop_pos:
                    dot.node('AuxP', cop_pos, shape='plaintext', fontsize='10', group='aux_group')
                    dot.edge('AUX:s', 'AuxP:n', weight='100'); dot.edge('AuxP:s', 'AuxW:n', weight='100')
                else:
                    dot.edge('AUX:s', 'AuxW:n', weight='100')
                terminal_words.append('AuxW'); ordered_bottom.append('AuxW')
            
            if items_between:
                last_conn_type_between = None
                current_peri_parent_between = None
                for i, item in enumerate(items_between):
                    if not item['text']: continue
                    uid = f"Between_{i}"
                    conn_type = item['conn_type']
                    if conn_type == 'Arg':
                        last_conn_type_between = None; current_peri_parent_between = None
                        top_id = f"{uid}_Top"
                        dot.node(top_id, item['label'], shape='plaintext', group=uid)
                        dot.edge('CORE:s', f'{top_id}:n', weight='1')
                        layer_nuc['center'].append(top_id); nuc_level_order.append(top_id)
                        wid = draw_word_structure(top_id, item, uid)
                        terminal_words.append(wid); ordered_bottom.append(wid)
                    else:
                        if conn_type == last_conn_type_between and current_peri_parent_between:
                            parent_id = current_peri_parent_between; uid_for_group = f"Between_{i}"
                        else:
                            parent_id = f"PERI_Between_{uid}"
                            dot.node(parent_id, "PERIPHERY", shape='plaintext', group=uid)
                            uid_for_group = uid
                            if conn_type == 'Peri-Clause':
                                target_layer_id = 'CL'; layer_cl['center'].append(parent_id)
                            elif conn_type == 'Peri-Core':
                                target_layer_id = 'CORE'; layer_core['center'].append(parent_id)
                            elif conn_type == 'Peri-Nuc':
                                target_layer_id = 'NUC'; layer_nuc['center'].append(parent_id); nuc_level_order.append(parent_id)
                            
                            dot.edge(f'{parent_id}:w', f'{target_layer_id}:e', arrowhead='normal', constraint='false', minlen='1')
                            last_conn_type_between = conn_type; current_peri_parent_between = parent_id
                        
                        item_top_id = f"{uid}_Top"
                        dot.node(item_top_id, item['label'], shape='plaintext', group=uid_for_group)
                        dot.edge(f'{parent_id}:s', f'{item_top_id}:n', weight='100')
                        wid = draw_word_structure(item_top_id, item, uid_for_group)
                        terminal_words.append(wid); ordered_bottom.append(wid)
            
            dot.node('PRED_A', 'PRED', shape='plaintext', fontsize='10', group='pred_attr')
            dot.node('AttrW', attr_word, shape='none', group='pred_attr')
            dot.edge('NUC:s', 'PRED_A:n', weight='100')
            nuc_level_order.append('PRED_A')
            
            if attr_pos:
                dot.node('AttrP', attr_pos, shape='plaintext', fontsize='10', group='pred_attr')
                dot.edge('PRED_A:s', 'AttrP:n', weight='100'); dot.edge('AttrP:s', 'AttrW:n', weight='100')
            else:
                dot.edge('PRED_A:s', 'AttrW:n', weight='100')
            terminal_words.append('AttrW'); ordered_bottom.append('AttrW')
            
            if len(nuc_level_order) > 1:
                for i in range(len(nuc_level_order) - 1):
                    dot.edge(nuc_level_order[i], nuc_level_order[i+1], style='invis', weight='10')
            
            if cop_word:
                with dot.subgraph() as s: s.attr(rank='same'); s.node('AUX'); s.node('PRED_A')

    process_item_group(items_post, 'Post')

    w_pocs = draw_slot('PoCS', pocs, 'CL', layer_core['post'])
    if w_pocs: ordered_bottom.append(w_pocs)
    w_podp = draw_slot('PoDP', podp, 'S', layer_cl['post'])
    if w_podp: ordered_bottom.append(w_podp)

    def enforce_rank(node_list):
        if not node_list: return
        with dot.subgraph() as s:
            s.attr(rank='same')
            for i, node_id in enumerate(node_list):
                s.node(node_id)
                if i > 0: s.edge(node_list[i-1], node_id, style='invis', weight='5')

    full_cl_list = layer_cl['pre'] + layer_cl['center'] + layer_cl['post']
    enforce_rank(full_cl_list)
    full_core_list = layer_core['pre'] + layer_core['center'] + layer_core['post']
    enforce_rank(full_core_list)
    full_nuc_list = layer_nuc['pre'] + layer_nuc['center'] + layer_nuc['post']
    enforce_rank(full_nuc_list)

    if terminal_words:
        # CORRECCIÓN DE SINTAXIS: Bucle en líneas separadas
        with dot.subgraph() as s: 
            s.attr(rank='sink')
            for n in terminal_words: 
                s.node(n)

    for i in range(len(ordered_bottom) - 1):
        dot.edge(ordered_bottom[i], ordered_bottom[i+1], style='invis', weight='10')

    return dot

# ==========================================
# INTERFACE
# ==========================================
try:
    st.image("albura_logo.png", width=400)
except:
    st.title("Albura")

st.caption("Assistant for diagramming RRG syntactic trees")
st.markdown("---")

main_c1, main_c2 = st.columns([1, 3])

with main_c1:
    st.subheader("Clause data")
    
    with st.expander("1. Nucleus", expanded=False):
        # Usamos get_key para que los campos se reseteen al cambiar el ID
        pred_type = st.radio("Type", ["Predicative", "Attributive"], horizontal=True, key=get_key("pred_type"))
        nucleus_data = {'text': '', 'pos': ''}
        copula_data = {'text': '', 'pos': ''}
        attribute_data = {'text': '', 'pos': ''}
        items_between_data = []
        
        if pred_type == "Predicative": 
            c1, c2 = st.columns([2, 1])
            nucleus_data['text'] = c1.text_input("Data", key=get_key("nuc_txt"))
            nucleus_data['pos'] = c2.text_input("PoS", key=get_key("nuc_pos"))
            p_type_key = 'verbal'
        else:
            st.markdown("**AUX (Copula)**")
            c1, c2 = st.columns([2, 1])
            copula_data['text'] = c1.text_input("Data", key=get_key("aux_txt"))
            copula_data['pos'] = c2.text_input("PoS", key=get_key("aux_pos"))
            
            st.markdown("---")
            st.markdown("**PRED (Attribute)**")
            c3, c4 = st.columns([2, 1])
            attribute_data['text'] = c3.text_input("Data", key=get_key("attr_txt"))
            attribute_data['pos'] = c4.text_input("PoS", key=get_key("attr_pos"))
            
            st.markdown("---")
            st.markdown("**Elements between AUX and PRED**")
            num_between = st.number_input("Number of items", min_value=0, value=0, key=get_key("num_between"))
            
            if num_between > 0:
                for i in range(num_between):
                    st.markdown(f"**Item {i+1}**")
                    conn_type_raw = st.selectbox(
                        "Type", 
                        ["Argument", "Periphery (NUC)", "Periphery (CORE)", "Periphery (CLAUSE)"], 
                        key=get_key(f"betw_c_{i}")
                    )
                    conn_map = {
                        "Argument": ("Arg", "XP"),
                        "Periphery (NUC)": ("Peri-Nuc", "XP"),
                        "Periphery (CORE)": ("Peri-Core", "XP"),
                        "Periphery (CLAUSE)": ("Peri-Clause", "XP")
                    }
                    code, def_lbl = conn_map[conn_type_raw]
                    c1, c2, c3 = st.columns([1, 2, 1])
                    lbl = c1.text_input("Label", value=def_lbl, key=get_key(f"betw_l_{i}"))
                    txt = c2.text_input("Data", key=get_key(f"betw_t_{i}"))
                    pos = c3.text_input("PoS", key=get_key(f"betw_p_{i}"))
                    items_between_data.append({
                        'label': lbl, 'text': txt, 'pos': pos, 'conn_type': code
                    })
            
            p_type_key = 'copular'

    with st.expander("2. Constituents", expanded=False):
        st.caption("Pre-nuclear")
        num_pre = st.number_input("Number of items", min_value=0, value=1, key=get_key("num_pre"))
        items_pre_data = []
        for i in range(num_pre):
            st.markdown(f"**Item {i+1}**")
            conn_type_raw = st.selectbox("Type", ["Argument", "Periphery (NUC)", "Periphery (CORE)", "Periphery (CLAUSE)"], key=get_key(f"pre_c_{i}"))
            conn_map = {"Argument": ("Arg", "XP"), "Periphery (NUC)": ("Peri-Nuc", "XP"), "Periphery (CORE)": ("Peri-Core", "XP"), "Periphery (CLAUSE)": ("Peri-Clause", "XP")}
            code, def_lbl = conn_map[conn_type_raw]
            c1, c2, c3 = st.columns([1, 2, 1])
            lbl = c1.text_input("Label", value=def_lbl, key=get_key(f"pre_l_{i}_{code}"))
            txt = c2.text_input("Data", key=get_key(f"pre_t_{i}")); pos = c3.text_input("PoS", key=get_key(f"pre_p_{i}"))
            items_pre_data.append({'label': lbl, 'text': txt, 'pos': pos, 'conn_type': code})
            
        st.caption("Post-nuclear")
        num_post = st.number_input("Number of items", min_value=0, value=0, key=get_key("num_post"))
        items_post_data = []
        for i in range(num_post):
            st.markdown(f"**Item {i+1}**")
            conn_type_raw = st.selectbox("Type", ["Argument", "Periphery (NUC)", "Periphery (CORE)", "Periphery (CLAUSE)"], key=get_key(f"post_c_{i}"))
            code, def_lbl = conn_map[conn_type_raw]
            c1, c2, c3 = st.columns([1, 2, 1])
            lbl = c1.text_input("Label", value=def_lbl, key=get_key(f"post_l_{i}_{code}"))
            txt = c2.text_input("Data", key=get_key(f"post_t_{i}")); pos = c3.text_input("PoS", key=get_key(f"post_p_{i}"))
            items_post_data.append({'label': lbl, 'text': txt, 'pos': pos, 'conn_type': code})

    with st.expander("3. Topics and foci"):
        def input_peri(label_ui, key_prefix, default_lbl="XP"):
            st.markdown(f"**{label_ui}**")
            c1, c2, c3 = st.columns([1, 2, 1])
            lbl = c1.text_input("Label", default_lbl, key=get_key(f"{key_prefix}_lbl"))
            txt = c2.text_input("Data", key=get_key(f"{key_prefix}_txt")); pos = c3.text_input("PoS", key=get_key(f"{key_prefix}_pos"))
            return {'label': lbl, 'text': txt, 'pos': pos}
        prcs = input_peri("PrCS", "prcs", "XP"); pocs = input_peri("PoCS", "pocs", "XP")
        prdp = input_peri("PrDP", "prdp", "XP"); podp = input_peri("PoDP", "podp", "XP")
    
    st.markdown("---")
    st.caption("by Carlos González Vergara (__cgonzalv@uc.cl__)")
    
    try:
        with open("cc_by_icon.png", "rb") as f:
            import base64
            img_data = base64.b64encode(f.read()).decode()
        st.markdown(f'<a href="https://creativecommons.org/licenses/by/4.0/" target="_blank"><img src="data:image/png;base64,{img_data}" alt="CC BY 4.0" width="88"></a>', unsafe_allow_html=True)
    except:
        st.markdown("[CC BY 4.0](https://creativecommons.org/licenses/by/4.0/)")

with main_c2:
    show_graph = False
    if p_type_key == 'verbal' and nucleus_data['text']: show_graph = True
    elif p_type_key == 'copular' and attribute_data['text']: show_graph = True

    if show_graph:
        data = {
            'prdp': prdp, 'prcs': prcs, 'pred_type': p_type_key, 
            'nucleus': nucleus_data, 'copula': copula_data, 'attribute': attribute_data,
            'items_between': items_between_data, 'items_pre': items_pre_data, 
            'items_post': items_post_data, 'pocs': pocs, 'podp': podp
        }
        graph = draw_lsc_tree(data)
        try:
            png_data = graph.pipe(format='png')
            btn_col1, btn_col2, btn_col3 = st.columns([0.12, 0.76, 0.12])
            with btn_col1:
                st.download_button("Download", png_data, "albura_tree.png", "image/png", use_container_width=True)
            with btn_col3:
                # El botón incrementa el contador, renovando las keys de los inputs
                st.button("New", use_container_width=True, on_click=reset_state, help="Generate new diagram")
            
            svg_code = graph.pipe(format='svg').decode('utf-8')
            
            # Limpieza del SVG para hacerlo responsive
            svg_code = re.sub(r'(width|height)="[^"]*"', '', svg_code)
            
            html_content = f"""
            <div style="border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px; background-color: white; box-sizing: border-box;">
                <div style="width: 100%; height: 600px; overflow: auto; display: flex; justify-content: center; align-items: flex-start; padding-top: 20px;">
                    <style>
                        svg {{ width: 100%; height: auto; max-height: 580px; }}
                        text {{ font-family: Helvetica, Arial, sans-serif !important; }}
                    </style>
                    {svg_code}
                </div>
            </div>
            """
            components.html(html_content, height=640, scrolling=False)
        except Exception as e: st.error(f"Technical error: {e}")
    else: st.info("Fill in the data to begin")