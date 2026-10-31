from zipfile import ZipFile, ZIP_DEFLATED
from lxml import etree as E
from pathlib import Path
import hashlib
src=Path('/Users/rodrigotriboni1/Downloads/Projeto_TCC_Rodrigo_Redes_Bayesianas (1) (1).docx')
out=Path('entregas/TCC_Research_Proposal_Rodrigo_English.docx')
W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'; ns={'w':W}
T={
0:'FEDERAL UNIVERSITY OF UBERLÂNDIA',
1:'SCHOOL OF ELECTRICAL ENGINEERING',
2:'CONTROL AND AUTOMATION ENGINEERING PROGRAM',
4:'BAYESIAN NETWORKS AND EXPECTED UTILITY APPLIED TO NEXT BEST ACTION SELECTION IN AUTOMATED DECISION SYSTEMS',
6:'Undergraduate thesis proposal submitted to the Control and Automation Engineering Program at the Federal University of Uberlândia (UFU), Santa Mônica Campus, in partial fulfillment of the requirements for enrollment in the Undergraduate Thesis course.',
7:'Supervisor: Prof. Dr. [Supervisor’s Name]',
11:'ABSTRACT',
12:'Automated decision systems, such as credit approval engines, traditionally separate risk estimation from action selection only implicitly, incorporating both into deterministic rules or weighted scores that are difficult to audit. This project proposes to formalize these two stages as distinct components of a single decision support system: a probabilistic layer, based on Bayesian networks, responsible for estimating the risk of a case from observed evidence; and a decision layer, based on expected utility, responsible for selecting the next best action from a set of admissible alternatives, using a utility function that weighs the costs, benefits, and constraints associated with each combination of action and outcome. A literature review on Bayesian networks, decision-making under uncertainty, and influence diagrams will be conducted, followed by the modeling and calibration of a Bayesian risk network using the public German Credit Data dataset, the definition of an illustrative utility function, and the implementation of an expected-utility-based action selection mechanism. The model will be evaluated separately in terms of predictive performance (discrimination and probability calibration) and decision policy performance, with comparisons against a logistic regression baseline and threshold rules. The expected outcome is to demonstrate that a decision policy grounded in calibrated Bayesian inference and explicit expected utility produces more consistent and transparent recommendations than approaches based solely on score thresholds.',
13:'Keywords: Bayesian Networks. Decision Systems. Next Best Action. Artificial Intelligence. Decision Automation.',
15:'CONTENTS',
27:'1 INTRODUCTION',
28:'The automation of decision-making processes is a central pillar of artificial intelligence applications in business systems, spanning domains as diverse as credit approval, service triage, predictive maintenance, and operational risk management. Historically, automated decision engines have been built on deterministic rules and weighted scores, in which business criteria are assigned fixed weights by domain experts. Although auditable, this approach has a structural limitation that has received limited attention: it combines the estimation of a case’s risk and the selection of an action in response to that risk within a single rule, without making the boundary between these two tasks explicit.',
29:'Bayesian networks are a class of probabilistic graphical models capable of explicitly representing conditional dependencies among random variables and performing inference under uncertainty (PEARL, 1988). When applied to a decision-making process, Bayesian networks are naturally suited to the first task: estimating the probability of a state or outcome, such as default risk, from observed evidence. However, an estimated probability is not, by itself, a recommended action. The action with the highest probability of success is not necessarily the action with the highest expected business value, since different actions involve different costs, benefits, and constraints. Transforming a risk estimate into a next best action recommendation therefore requires an additional decision layer grounded in expected utility theory, which purely predictive models do not inherently provide (JENSEN; NIELSEN, 2007).',
30:'This project proposes to investigate this explicit separation between inference and decision-making by organizing the proposed system into three components: (i) a Bayesian network that estimates risk probability from evidence; (ii) a set of admissible actions defined for methodological purposes rather than as an actual credit approval policy; and (iii) an expected utility function that ranks these actions and selects the recommendation with the highest expected value. The case study uses the public German Credit Data dataset exclusively to model the risk layer. Since the dataset contains neither historical observations of actions nor their counterfactual outcomes, the decision layer will explicitly be evaluated as a methodological simulation rather than as validation of an actual policy.',
31:'1.1 Rationale',
32:'The choice of topic is justified, first, by its direct alignment with the foundations of the Control and Automation Engineering program, particularly decision systems under uncertainty, probabilistic modeling, and the automation of decision-making processes, extended through artificial intelligence techniques and decision theory. Treating the decision engine as a supervisory decision support layer, in which a Bayesian network estimates a risk state that is not directly observable and a separate decision component selects an action based on expected utility, highlights the convergence between estimation under uncertainty, a central topic in automation, and the automation of business decisions. This does not improperly equate the architecture with a classical dynamic control loop, since there is neither physical feedback nor a controlled variable in the strict sense.',
33:'Second, the topic has immediate practical relevance: decision systems that treat risk and action as a single stage tend to conceal the actual criterion behind each recommendation, making decisions harder to audit and justify. Making the utility function explicit increases the transparency of the decision engine and enables analysis of its sensitivity to changes in business criteria. Finally, the author of this proposal works professionally on the development of automation and artificial intelligence platforms for business decision processes, including credit engines based on rules and weighted scores. This provides practical familiarity with the auditability and opacity issues that the separation between inference and decision-making seeks to address. It does not entail using proprietary data or systems from any specific organization, since the study uses only the public German Credit Data dataset.',
34:'1.2 Objectives',
35:'The overall objective of this study is to develop and evaluate a probabilistic decision support system based on a Bayesian network that can estimate risk under uncertainty and select a next best action through an explicit expected utility policy, using the public German Credit Data dataset as a case study.',
36:'The specific objectives are to:',
37:'Conduct a literature review on Bayesian networks, decision-making under uncertainty, influence diagrams, and next best action systems;',
38:'Model and calibrate the probability of the credit outcome using the evidence available in German Credit Data;',
39:'Compare different strategies for defining the Bayesian network structure, guided by domain knowledge and/or learned from data;',
40:'Compare the predictive quality of the Bayesian network with a logistic regression/scorecard baseline;',
41:'Define an illustrative set of admissible actions and a documented utility function with explicit costs and benefits;',
42:'Implement a mechanism for selecting and ranking actions by expected utility (next best action);',
43:'Evaluate the predictive performance of the risk model separately from the performance of the decision policy, including sensitivity analysis of the utilities adopted;',
44:'Implement a simple, reproducible prototype demonstrating the complete workflow: evidence, estimated risk, recommended action, and justification.',
45:'2 LITERATURE REVIEW',
46:'This section presents the main concepts and studies underpinning the proposed development, covering Bayesian networks and probabilistic graphical models, decision-making under uncertainty and influence diagrams, and next best action systems.',
47:'2.1 Bayesian Networks and Probabilistic Graphical Models',
48:'Bayesian networks are probabilistic graphical models that represent a set of random variables and their conditional dependencies through a directed acyclic graph. Nodes correspond to variables, and edges represent direct dependency relationships quantified by conditional probability tables (PEARL, 1988). This structure enables exact or approximate inference over the joint probability distribution of the variables, even when the available evidence is incomplete or noisy, making the formalism particularly suitable for decision-making under uncertainty (KOLLER; FRIEDMAN, 2009).',
49:'From a model-learning perspective, constructing a Bayesian network involves two stages: defining the graph structure, which may be specified through domain knowledge or learned from data using structure search algorithms guided by criteria such as BIC or BDeu; and estimating the parameters of the conditional distributions, typically through maximum likelihood or Bayesian methods with prior distributions that smooth small counts. Russell and Norvig (2010) discuss these stages in the broader context of artificial intelligence systems based on probabilistic reasoning, positioning Bayesian networks as one of the main tools for representing uncertain knowledge in intelligent systems.',
50:'2.2 Decision-Making under Uncertainty and Influence Diagrams',
51:'Estimating the probability of a state is not, by itself, sufficient to recommend an action: a criterion that translates probability into value is required. Decision theory under uncertainty formalizes this criterion through expected utility, according to which the rational action is the one that maximizes EU(a|x) = Σ P(y|a,x)·U(a,y), where x denotes the observed evidence, a is a candidate action, y is a possible outcome, and U(a,y) is the utility assigned to the combination of action and outcome (RUSSELL; NORVIG, 2010). Influence diagrams, or decision networks, extend Bayesian networks by explicitly incorporating decision nodes and utility nodes alongside traditional chance nodes. This allows both uncertainty about the system state and the process of choosing the optimal action to be represented in a single graph (HOWARD; MATHESON, 2005; JENSEN; NIELSEN, 2007).',
52:'This distinction is central to this study: a model that only classifies risk answers the question “What is the probability that this case is high risk?” but not “Which action should be taken?” The second question requires an explicit definition of admissible actions and a utility function. Without these, any action recommendation risks confusing a higher probability of success with higher expected business value, which may diverge whenever actions involve different costs or benefits (JENSEN; NIELSEN, 2007).',
53:'2.3 Next Best Action Systems and Credit Scoring',
54:'Scoring models, widely used in domains such as credit approval, risk triage, and service prioritization, are the classical approach to automating business decisions. They assign weights to predictor variables using statistical techniques such as logistic regression and have been adopted by industry because of their interpretability and ease of auditing (THOMAS, 2000; SIDDIQI, 2012). However, these approaches essentially treat the decision as a binary classification between approval and denial, or acceptance and rejection, applying a threshold to the score without making the underlying utility function explicit.',
55:'The concept of next best action, originating in the literature on marketing analytics and recommender systems, proposes structuring a decision as the selection, from a set of possible actions, of the action that maximizes an expected value metric given the characteristics of the case being analyzed. Established credit datasets, such as German Credit Data, typically provide only a binary risk outcome (good or bad credit), rather than historical observations of multiple actions and their respective outcomes. Consequently, next best action systems built on these data cannot learn an action policy through supervised learning; the risk estimate must be combined with a decision layer explicitly defined by the designer, as discussed in Section 2.2.',
56:'3 METHODOLOGY',
57:'This study will follow a structured approach consisting of sequential stages, with the validation protocol defined before any model is trained to prevent information leakage between fitting and evaluation. The stages are described below.',
58:'Stage A – Formalization of the Research Question and Experimental Protocol',
59:'Formalize the central research question, for example: does a decision policy based on calibrated Bayesian network probabilities and expected utility produce more consistent decisions than a score/threshold policy in the German Credit case study? Precisely define the outcome to be modeled, its coding, and its prevalence in the dataset, as well as the validation protocol to be followed, using a held-out test set or stratified cross-validation, before any model fitting takes place.',
60:'Stage B – Exploratory Analysis and Preprocessing Pipeline',
61:'Conduct exploratory analysis of German Credit Data, including distributions, categorical variable cardinality, dependencies, redundancies, and class balance, documenting all transformations applied. Build the preprocessing pipeline, including discretization of continuous variables where required for Bayesian modeling, taking explicit care to fit any discretization or structure selection only within the training subset of each split, thereby preventing test-set information leakage.',
62:'Stage C – Baseline and Bayesian Risk Network Modeling',
63:'Build a logistic regression/scorecard baseline with calibrated probabilities as a robust and defensible predictive reference. In parallel, build the Bayesian risk network: define an initial structure guided by domain knowledge, compare it with a structure learned from data using criteria such as BIC or BDeu, and estimate the conditional probability table parameters using smoothing/priors to reduce the effect of small counts in a dataset of approximately one thousand records.',
64:'Stage D – Decision Layer: Actions and Expected Utility',
65:'Define an illustrative set of admissible actions, such as approving, requesting additional information or collateral, referring for manual review, and rejecting, treating them as a methodological demonstration rather than an actual credit approval policy. Construct a documented and transparent utility/cost matrix that assigns a value to each combination of action and outcome. Implement the next best action selection mechanism using expected utility, EU(a|x) = Σ P(y|a,x)·U(a,y), ranking candidate actions and recording the second-best alternative and the utility difference between them.',
66:'Stage E – Validation, Sensitivity, and Robustness',
67:'Evaluate two dimensions of the system separately: the predictive performance of the risk model (ROC-AUC, PR-AUC where appropriate, Brier score, log loss, and calibration diagram) and the performance of the decision policy (mean expected utility, expected cost, and distribution of recommended actions). Compare the Bayesian policy with the policy derived from the baseline using threshold rules. Perform sensitivity analysis of the utility matrix to determine whether small changes in the adopted costs and benefits alter the recommendation, and test model robustness to incomplete evidence, exploring the ability of probabilistic inference to operate with partial information.',
68:'Stage F – Prototype Implementation and Explainability',
69:'Implement a simple prototype, for example using Streamlit, demonstrating the complete system workflow: case evidence input, estimated risk probability, ranking of actions by expected utility, and justification of the recommendation, including the most relevant evidence and the change relative to the prior probability. The interface will serve as the final demonstration of the study rather than the central methodological contribution and will be developed only after methodological validation has been completed.',
70:'Stage G – Writing the Final Thesis',
71:'Write the thesis continuously throughout the semester, incrementally consolidating the results obtained at each stage, critically discussing the limitations of the model and evaluation, and organizing the final text according to institutional requirements.',
72:'Stage H – Final Review and Presentation Preparation',
73:'Conduct a final review of the text and results, ensure reproducibility by fixing random seeds, recording library versions, and providing the data preparation notebook/script, training pipeline, and experimental configuration, and prepare the presentation for the examining committee.',
74:'4 SCHEDULE',
75:'The study will be carried out during the second academic semester of 2026, beginning in September 2026 and concluding in December 2026, according to the distribution of stages presented in Table 1.',
76:'Table 1 – Distribution of the proposed stages.',
77:'Source: Prepared by the author.',
78:'5 REQUIRED RESOURCES',
79:'The following resources will be required to carry out this project:',
80:'A personal computer with sufficient processing capacity to train probabilistic models;',
81:'A Python development environment with libraries for Bayesian network modeling, such as pgmpy or equivalent libraries supporting influence diagrams; logistic regression and statistical evaluation, including scikit-learn, pandas, and numpy; and, for the final prototype, a simple interface library such as Streamlit;',
82:'The public German Credit Data (Statlog) dataset, available from the UCI Machine Learning Repository, without reliance on proprietary data from any specific organization;',
83:'Access to specialized scientific literature through the CAPES Journals Portal and databases provided by the UFU Library System;',
84:'Regular supervision by the faculty advisor to provide technical validation of the modeling and model evaluation stages.',
85:'All necessary computing resources are already available to the author, and no additional equipment or software purchases will be required to carry out this project.',
86:'REFERENCES',
88:'HOFMANN, H. Statlog (German Credit Data) Data Set. UCI Machine Learning Repository, 1994. Available at: https://archive.ics.uci.edu/ml/datasets/statlog+(german+credit+data).',
89:'HOWARD, R. A.; MATHESON, J. E. Influence diagrams. Decision Analysis, v. 2, n. 3, p. 127–143, 2005 (reprint of the original 1984 work).',
90:'JENSEN, F. V.; NIELSEN, T. D. Bayesian Networks and Decision Graphs. 2nd ed. New York: Springer, 2007.',
93:'RUSSELL, S.; NORVIG, P. Inteligência Artificial. 3rd ed. Rio de Janeiro: Elsevier, 2010.',
94:'SIDDIQI, N. Credit Risk Scorecards: Developing and Implementing Intelligent Credit Scoring. 2nd ed. Hoboken: John Wiley & Sons, 2012.'
}
toc={16:27,17:31,18:34,19:45,20:47,21:50,22:53,23:56,24:74,25:78,26:86}
# Page numbers are updated after rendering the translated document.
for a,b in toc.items(): T[a]=T[b]
with ZipFile(src) as z: parts={n:z.read(n) for n in z.namelist()}
r=E.fromstring(parts['word/document.xml']); ps=r.find('w:body',ns).findall('w:p',ns)
def replace(p,s):
 ts=p.findall('.//w:t',ns)
 assert ts
 ts[0].text=s
 for t in ts[1:]: t.text=''
for i,s in T.items(): replace(ps[i],s)
rows=r.findall('.//w:tbl/w:tr',ns)
labels=['Stage','A – Question, review, and protocol','B – EDA and preprocessing pipeline','C – Baseline and Bayesian network','D – Decision layer/NBA','E – Validation and sensitivity','F – Interface/prototype','G – Thesis writing','H – Final review and presentation']
for i,row in enumerate(rows):
 cells=row.findall('w:tc',ns); replace(cells[0],labels[i])
 if i==0:
  for c,label in zip(cells[1:],['SEP 2026','OCT 2026','NOV 2026','DEC 2026']): replace(c,label)
# Set proofing language while preserving original section geometry and typography.
for p in ps:
 for run in p.findall('w:r',ns):
  pr=run.find('w:rPr',ns)
  if pr is None: pr=E.Element('{'+W+'}rPr');run.insert(0,pr)
  lang=pr.find('w:lang',ns)
  if lang is None: lang=E.SubElement(pr,'{'+W+'}lang')
  lang.set('{'+W+'}val','en-US')
parts['word/document.xml']=E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(out,'w',ZIP_DEFLATED) as z:
 for n,b in parts.items():z.writestr(n,b)
Path('.documentos_qa/english_coverage.txt').write_text('Translated paragraph indices: '+str(sorted(T))+'\nPreserved: proper names, blank paragraphs, bibliographic titles and English references.\nSource SHA256: '+hashlib.sha256(src.read_bytes()).hexdigest())
print(out.resolve())
