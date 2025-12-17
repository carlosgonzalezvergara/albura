import streamlit as st
import pandas as pd

st.set_page_config(
    page_title="Albura — User Manual",
    page_icon="📘",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# Custom CSS para mejorar la estética
st.markdown("""
    <style>
    .main {
        background-color: #fafafa;
    }
    .stAlert {
        border-radius: 10px;
    }
    .stExpander {
        border: none !important;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        background-color: white;
        margin-bottom: 10px;
    }
    h1, h2 {
        color: #1E3A8A;
    }
    </style>
""", unsafe_allow_html=True)

# --- Navigation ---
top_l, top_r = st.columns([0.8, 0.2])
with top_l:
    st.page_link("albura.py", label=" Return to Albura", icon="🏠")

st.divider()

# --- Header Section ---
st.title("User Manual")
st.markdown("""
    **Albura** is a specialized tool for linguists to create high-quality diagrams of the 
    **Layered Structure of the Clause (LSC)** according to Role and Reference Grammar (RRG).
    """)

# --- Introduction Tabs ---
tab_intro, tab_interface, tab_workflow, tab_tech = st.tabs([
    "✨ Introduction", "🖥️ Interface", "🛠️ Workflow", "📊 Abbreviations"
])

with tab_intro:
    st.subheader("What is Albura?")
    st.write("""
        The name **Albura** refers in Spanish to the *sapwood* (the living, outermost part of a tree trunk).
             
        I thought it was a nice metaphor. (Thanks, Jakie! ❤️).
    """)
    
    st.success("""
        **Core Features:**
        * **Constituent Projection:** Visualize the hierarchy from Sentence down to Word level.
        * **Operator Projection:** Map grammatical categories (Tense, Aspect, Modality, etc.) clearly.
        * **Morphological Precision:** Distinct handling for affixes and clitics.
        * **Publication Ready:** Export in high-resolution PNG.
    """)

with tab_interface:
    st.subheader("Layout Overview")
    c1, c2 = st.columns(2)
    with c1:
        st.markdown("""
        #### 1. Input Panel (Left)
        Organized in logical accordions:
        1. **Nucleus:** Predicative verbs or Auxiliary plus predicative elements.
        2. **Arguments and Adjuncts**: Argumental constituents linked to the CORE (or COREw) layer, and peripheral constituents.
        3. **Topics and Foci:** Pre/Post-Detached Positions, and Pre/Post-Core Slots.
        4. **Extra-Core Slots:** Syntactic extra constituents used when the argument is morphological (Head-marking languages).
        5. **Operators:** The functional projection.
        """)
    with c2:
        st.markdown("""
        #### 2. Visualizer (Right)
        * **Real-time Rendering:** Watch the tree grow as you type.
        * **Quick Reset:** Use the **"New"** button to clear the state and start fresh.
        """)

with tab_workflow:
    st.subheader("Recommended Step-by-Step")
    
    with st.expander("1. Define the Nucleus (Mandatory)", expanded=True):
        st.write("Choose between **Predicative** or **Attributive**.")
        st.write("You can put constituents (arguments and adjuncts) that appear between AUX and NUC if you need to.")
        st.caption("Note: The diagram will not appear until the Nucleus text is entered.")

    with st.expander("2. Add Constituents", expanded=False):
        st.write("Add items from leftmost to rightmost.")
        st.markdown("""
        * **Pre-nuclear:** Elements before the verb.
        * **Post-nuclear:** Elements after the verb.
        * **Morphology:** Select 'Morphological' for affixes/clitics to attach them to the **COREw/NUCw** nodes.
        """)

    with st.expander("3. Configure Operators", expanded=False):
        st.write("Operators are scoped by layer (Nucleus, Core, or Clause).")
        st.markdown("""
        1.  **Define Realization Forms:** If an operator is an affix or particle not yet in the tree, add it here first.
        2.  **Add Operators:** Select the type (e.g., Aspect) and use the **'Links to'** multi-select to draw dashed lines to specific item(s).
        """)

with tab_tech:
    st.subheader("RRG Abbreviations Reference")
    abbr_data = [
        {"Category": "Layer", "Abbr": "NUC / CORE / CL", "Meaning": "Nucleus / Core / Clause"},
        {"Category": "Slots", "Abbr": "PrDP / PoDP", "Meaning": "Pre- and Post-Detached Positions"},
        {"Category": "Slots", "Abbr": "PrCS / PoCS", "Meaning": "Pre- and Post-Core Slots"},
        {"Category": "Word Level", "Abbr": "COREw / NUCw", "Meaning": "Morphological word nodes"},
        {"Category": "Morph", "Abbr": "AFF / CL", "Meaning": "Affix / Clitic"},
        {"Category": "Operators", "Abbr": "ASP / TNS / IF", "Meaning": "Aspect / Tense / Illocutionary Force"},
    ]
    st.table(pd.DataFrame(abbr_data))

st.divider()

# --- Practical Tips Section ---
st.header("💡 Expert Tips")
col1, col2 = st.columns(2)

with col1:
    st.markdown("""
    **Best Practices:**
    - Always fill the diagram starting with the Nucleus information and go down from there.
    - **Linearity:** Always enter elements from left-to-right.
    - **Copulas:** Use the "Items between AUX and PRED" feature for arguments or adjuncts located between the auxiliary word and the predicator.
    - **Labels:** Use standard abbreviations (NP, PP, AdvP) for cleaner diagrams.
    - **PoS:** This is a space where you can add optional information (e.g., part of sentence).
    """)

with col2:
    st.markdown("""
    **Troubleshooting:**
    - **Empty Screen:** Check if you have filled the 'Data' field in the Nucleus section.
    - **Dashed Lines:** If an operator line isn't showing, ensure you have selected a target in the 'Links to' dropdown.
    - **Alignment:** If the tree looks 'crowded', try simplifying the PoS labels.
    """)

st.divider()

# --- Footer ---
f1, f2 = st.columns([0.7, 0.3])
with f1:
    st.markdown("""
        ### Contact & License
        Developed by **Carlos González Vergara** (cgonzalv@uc.cl).  
        This tool is provided under the **Creative Commons BY 4.0** license.
    """)
with f2:
    try:
        st.image("cc_by_icon.png", width=150)
    except:
        st.markdown("**(CC BY 4.0)**")