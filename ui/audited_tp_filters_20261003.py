"""A compact TP eligibility explanation beside the existing price column."""
from core.execution_policy_20261003 import get_policy


def render_tp_checks(st,frame):
    p=get_policy()
    with st.expander('TP checks and entry eligibility',expanded=False):
        hours=', '.join(f'{h:02d}:00' for h in p.check_hours)
        st.caption(f'Entry checks: {hours} ({p.entry_timezone}). Up to {p.max_new_symbols} new symbols per check. Maximum holding time: {p.max_hold_hours} elapsed hours. Stop budget: {p.max_stop_pips:g} pips.')
        st.caption('Four ranked display slots remain available. A display slot becomes an eligible order only after its strategy, TP/SL, execution-data and validation checks pass.')
        if 'entry_eligible' in frame:
            count=int(frame.entry_eligible.fillna(False).astype(bool).sum())
            st.write(f'Eligible signals in this table: {count}')
        columns=[c for c in ('Symbol','Suggested TP','Suggested SL','TP Filter Pass Count','TP Filter Total Count','entry_eligible','research_entry_eligible','TP Filter Reasons') if c in frame]
        if columns:st.dataframe(frame[columns],hide_index=True,use_container_width=True)
        flags=[c for c in frame if c.startswith('TP Filter ') and c not in ('TP Filter Reasons','TP Filter Pass Count','TP Filter Total Count')]
        if flags and 'Symbol' in frame:st.dataframe(frame[['Symbol',*flags]],hide_index=True,use_container_width=True)
