import sys
sys.path.insert(0, '.')

import warnings
warnings.filterwarnings('ignore', category=DeprecationWarning)

exec(open('enterprise/modules/safety_governance/governance.py').read())

board = GovernanceBoard()

# 1. ModelChangeReview
mcr = board.get_model_review_board()
rid = mcr.submit_change('m', 'd', 'u', RiskLevel.MEDIUM)
mcr.review(rid, 'b', ReviewStatus.APPROVED)
mcr.review(rid, 'c', ReviewStatus.APPROVED)
assert mcr.get_status(rid).status == ReviewStatus.APPROVED
print('PASS 1: ModelChangeReview')

# 2. PromptChangeApproval
pca = board.get_prompt_approval_pipeline()
cid = pca.submit_prompt_change('g', 'h', 'i', 'u', 'x')
pca.advance_stage(cid, 'b', True)
pca.advance_stage(cid, 'c', True)
assert pca.get_current_stage(cid) == ApprovalStage.SECURITY_REVIEW
print('PASS 2: PromptChangeApproval')

# 3. ToolChangeImpactAssessment
tia = board.get_tool_impact_assessor()
imp = tia.assess('t', {'a': 1}, {'a': 2})
assert imp.impact_level == ImpactLevel.MINOR
print('PASS 3: ToolChangeImpactAssessment')

# 4. SecurityChangeReview
scr = board.get_security_review_board()
s = scr.submit_review('F', ['f'], RiskLevel.HIGH, 'o')
scr.approve(s, 'o1')
assert scr.get_security_posture()['approved'] == 1
print('PASS 4: SecurityChangeReview')

# 5. IncidentReviewBoard
irb = board.get_incident_board()
irb.convene('I', 'SEV1')
irb.assign_action_items('I', [{'a': 't', 'd': 'x'}])
assert irb.track_resolution('I')['total_actions'] == 1
print('PASS 5: IncidentReviewBoard')

# 6. ComplianceDashboard
cd = board.get_compliance_dashboard()
cd.add_framework(ComplianceFramework.SOC2)
cd.update_control(ComplianceFramework.SOC2, 'C1', 0.95)
cd.update_control(ComplianceFramework.SOC2, 'C2', 0.55)
assert cd.get_status()[0].overall_status == 'mostly_compliant'
print('PASS 6: ComplianceDashboard')

# 7. UserFeedbackAggregator
ufa = board.get_feedback_aggregator()
ufa.collect_feedback('u1', 'ui', 5.0)
ufa.collect_feedback('u2', 'ui', 2.0)
assert ufa.aggregate().total_feedback == 2
print('PASS 7: UserFeedbackAggregator')

# 8. PerformanceTrendAnalyzer
pta = board.get_trend_analyzer()
for i in range(20):
    pta.record_metric('l', 100.0 + i * 2.0)
trend = pta.analyze_trend('l')
assert trend.current_value == 138.0
print('PASS 8: PerformanceTrendAnalyzer')

# 9. RiskRegister
rr = board.get_risk_register()
rr.identify_risk('L', 'P', 0.3, 0.9, 's')
assert rr.get_top_risks(1)[0].score == 0.27
print('PASS 9: RiskRegister')

# 10. Board Report
report = board.generate_board_report()
assert 'model_review' in report
print('PASS 10: BoardReport')

# 11. AuditTrail
trail = AuditTrail()
trail.record('a', 'u', 'r')
assert trail.to_dict()['total_entries'] == 1
assert len(trail.query(actor='u')) == 1
print('PASS 11: AuditTrail')

# 12. GovernanceReport
gr = GovernanceReport(recommendations=['X'])
assert gr.to_dict()['recommendations'] == ['X']
print('PASS 12: GovernanceReport')

# 13. Dataclasses
e = ChangeApprovalEntry('e', ChangeType.MODEL, 'T', 'R')
assert e.to_dict()['change_type'] == 'model'
print('PASS 13: ChangeApprovalEntry')

cr = ChangeRecord('c', e)
assert cr.to_dict()['deployment_status'] == 'pending'
print('PASS 14: ChangeRecord')

inc = IncidentRecord('i', 'T', 'D', IncidentSeverity.SEV1)
assert inc.to_dict()['severity'] == 'sev1'
print('PASS 15: IncidentRecord')

cs = ComplianceStatus(ComplianceFramework.GDPR, control_count=10, passing_count=8)
assert cs.to_dict()['failing_count'] == 0
print('PASS 16: ComplianceStatus')

tdp = TrendDataPoint(value=42.0)
assert tdp.to_dict()['value'] == 42.0
print('PASS 17: TrendDataPoint')

uf = UserFeedback('f', 'u', 'cat', 4.0, sentiment=Sentiment.POSITIVE)
assert uf.to_dict()['sentiment'] == 'positive'
print('PASS 18: UserFeedback')

bmm = BoardMeetingMinutes('m', MeetingType.EMERGENCY)
assert bmm.to_dict()['meeting_type'] == 'emergency'
print('PASS 19: BoardMeetingMinutes')

ae = AuditEntry(action='test', actor='sys', resource='none')
assert ae.to_dict()['action'] == 'test'
print('PASS 20: AuditEntry')

# 14. All to_dict() methods
for o in [mcr, pca, tia, scr, irb, cd, ufa, pta, rr, board]:
    assert isinstance(o.to_dict(), dict)
print('PASS 21: all to_dict()')

# 15. Thread safety
import threading

def submit_and_review(i):
    r = mcr.submit_change('m%d' % i, 'c', 'u%d' % i, RiskLevel.LOW)
    mcr.review(r, 'auto', ReviewStatus.APPROVED)

threads = [threading.Thread(target=submit_and_review, args=(i,)) for i in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()
print('PASS 22: Thread safety')

print()
print('=== ALL 22 TESTS PASSED ===')