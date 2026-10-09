"""Small deterministic research baselines, never a trading decision service."""
from collections import Counter
import math
import numpy as np
import sklearn
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.metrics import (roc_auc_score, average_precision_score, log_loss,
    brier_score_loss, balanced_accuracy_score, confusion_matrix, accuracy_score,
    precision_score, recall_score, f1_score)

from .market_data import digest
from .p8_evidence import NUMERIC, CATEGORIES, SCHEMA_ID, LABEL_POLICY, folds, stamp, validate_features

POLICY = dict(version='p8-baselines-v1', seed=314159, models=['prior','logistic','shallow_tree'],
    folds='expanding elapsed time: 40/20/20/20%; 4H UTC floor; exact final boundary',
    thresholds=[.5,.6,.7],primary_threshold=.5,threshold_selection='FIXED_BEFORE_EVALUATION',
    logistic=dict(C=1.0,max_iter=2000,solver='lbfgs'),
    tree=dict(max_depth=3,min_samples_leaf=20),
    support=dict(train_total=100,train_per_class=20,test_total=50,test_per_class=10),
    support_meaning='Technical metric support only, not proof of statistical independence',
    qualification='PASS_THROUGH until independent window and full human-approved evidence gate are proven',
    commission='NOT_INCLUDED',costs='P6 BID/ASK plus 5% stop-distance slippage on each side',
    execution_eligible=False)
POLICY_ID=digest(POLICY)


def metrics(y, p):
    y=np.asarray(y,dtype=int); p=np.asarray(p,dtype=float)
    if len(y)==0: return dict(status='NOT_APPLICABLE',count=0)
    if len(y)!=len(p) or not np.isfinite(p).all() or np.any((p<0)|(p>1)):
        raise ValueError('Invalid prediction')
    if not set(y)<= {0,1}: raise ValueError('Invalid binary label')
    pred=(p>=.5).astype(int); both=len(set(y))==2
    bins=[]
    for lo in np.arange(0,1,.2):
        mask=(p>=lo)&(p<(lo+.2) if lo<.8 else p<=1)
        if mask.any(): bins.append(dict(lower=round(float(lo),2),count=int(mask.sum()),
            predicted=float(p[mask].mean()),observed=float(y[mask].mean())))
    return dict(status='VALID' if both else 'ONE_CLASS; rank metrics NOT_APPLICABLE',count=len(y),
        prevalence=float(y.mean()),roc_auc=float(roc_auc_score(y,p)) if both else None,
        pr_auc=float(average_precision_score(y,p)) if both else None,
        pr_auc_definition='average precision; not trapezoidal PR area',
        log_loss=float(log_loss(y,p,labels=[0,1])),brier=float(brier_score_loss(y,p)),
        accuracy=float(accuracy_score(y,pred)),
        balanced_accuracy=float(balanced_accuracy_score(y,pred)) if both else None,
        precision=float(precision_score(y,pred,zero_division=0)),
        recall=float(recall_score(y,pred,zero_division=0)),f1=float(f1_score(y,pred,zero_division=0)),
        confusion_matrix=confusion_matrix(y,pred,labels=[0,1]).tolist(),calibration=bins,
        expected_calibration_error=sum(b['count']*abs(b['predicted']-b['observed']) for b in bins)/len(y))


def trade_stats(rows):
    ordered=sorted(rows,key=lambda r:(stamp(r['resolved_at']),r['id']))
    values=[r['r_multiple'] for r in ordered]
    equity=peak=dd=0.
    for v in values:
        equity+=v; peak=max(peak,equity); dd=max(dd,peak-equity)
    gains=sum(max(0,v) for v in values); losses=sum(max(0,-v) for v in values)
    return dict(count=len(values),expectancy=sum(values)/len(values) if values else None,
        total_r=sum(values),max_drawdown_r=dd,profit_factor=gains/losses if losses else None,
        drawdown_basis='independent resolved research trades; resolution-order R sum, NOT account equity')


def filter_stats(rows, probabilities, threshold):
    kept=[r for r,p in zip(rows,probabilities) if p>=threshold]
    return dict(threshold=threshold,before=trade_stats(rows),after=trade_stats(kept),
        coverage=len(kept)/len(rows) if rows else None,rejected=len(rows)-len(kept))


def matrix(rows,categories):
    return np.array([[np.nan if r['features'][k] is None else r['features'][k]
                     for k in NUMERIC]+[r['features'][k] for k in categories] for r in rows],dtype=object)


def train(train_rows, test_rows, kind, *, strategy_id=True):
    categories=CATEGORIES if strategy_id else CATEGORIES[:-1]
    y=np.array([r['label'] for r in train_rows],dtype=int)
    if not len(y) or len(set(y))!=2: raise ValueError('Training requires both classes')
    config=dict(policy_hash=POLICY_ID,kind=kind,strategy_id=strategy_id,sklearn=sklearn.__version__,
        numpy=np.__version__,schema_id=SCHEMA_ID,label_policy=LABEL_POLICY,
        train_ids_hash=digest([r['id'] for r in train_rows]),seed=POLICY['seed'])
    if kind=='prior':
        artifact=dict(configuration=config,prior=float(y.mean()),type='constant_positive_prior')
        return np.repeat(y.mean(),len(test_rows)).tolist(),artifact
    numeric=Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=True,keep_empty_features=True)),
                      ('scale',StandardScaler())])
    transform=ColumnTransformer([('numeric',numeric,list(range(len(NUMERIC)))),
        ('category',OneHotEncoder(handle_unknown='ignore',sparse_output=False),
         list(range(len(NUMERIC),len(NUMERIC)+len(categories))))],verbose_feature_names_out=True)
    x=transform.fit_transform(matrix(train_rows,categories)).astype(float)
    xt=transform.transform(matrix(test_rows,categories)).astype(float)
    model=(LogisticRegression(**POLICY['logistic'],random_state=POLICY['seed']) if kind=='logistic'
           else DecisionTreeClassifier(**POLICY['tree'],random_state=POLICY['seed']))
    model.fit(x,y)
    names=transform.get_feature_names_out([*NUMERIC,*categories]).tolist()
    num=transform.named_transformers_['numeric']; imp=num.named_steps['impute']; scale=num.named_steps['scale']
    preprocessing=dict(numeric=list(NUMERIC),categories=list(categories),medians=imp.statistics_.tolist(),
        missing_indicators=imp.indicator_.features_.tolist(),mean=scale.mean_.tolist(),scale=scale.scale_.tolist(),
        category_values=[v.tolist() for v in transform.named_transformers_['category'].categories_],
        output_names=names,fit_on_train_only=True)
    if kind=='logistic':
        state=dict(coef=model.coef_[0].tolist(),intercept=float(model.intercept_[0]),
            associations=dict(zip(names,model.coef_[0].tolist())),interpretation='association, not causality')
    else:
        t=model.tree_
        state=dict(children_left=t.children_left.tolist(),children_right=t.children_right.tolist(),
            feature=t.feature.tolist(),threshold=t.threshold.tolist(),value=t.value.tolist(),
            importance=dict(zip(names,model.feature_importances_.tolist())),
            interpretation='native split importance, not causal')
    artifact=dict(configuration=config,preprocessing=preprocessing,state=state,type=kind)
    probabilities=model.predict_proba(xt)[:,1].tolist()
    if not np.allclose(probabilities,predict_artifact(artifact,test_rows),rtol=0,atol=1e-12):
        raise ValueError('Portable model artifact replay mismatch')
    return probabilities,artifact


def predict_artifact(artifact,rows):
    """Portable JSON research replay; no pickle or execution API."""
    if artifact['type']=='constant_positive_prior': return [artifact['prior']]*len(rows)
    prep=artifact['preprocessing']; state=artifact['state']; result=[]
    for r in rows:
        validate_features(r['features']); f=r['features']
        values=[prep['medians'][i] if f[k] is None else f[k] for i,k in enumerate(prep['numeric'])]
        values += [float(f[prep['numeric'][i]] is None) for i in prep['missing_indicators']]
        values=[(v-m)/s for v,m,s in zip(values,prep['mean'],prep['scale'])]
        values += [float(f[k]==v) for k,vs in zip(prep['categories'],prep['category_values']) for v in vs]
        if artifact['type']=='logistic':
            z=sum(v*c for v,c in zip(values,state['coef']))+state['intercept']
            p=1/(1+math.exp(-z)) if z>=0 else math.exp(z)/(1+math.exp(z))
        else:
            node=0
            while state['children_left'][node]!=-1:
                node=state['children_left'][node] if values[state['feature'][node]]<=state['threshold'][node] else state['children_right'][node]
            v=state['value'][node][0]; p=v[1]/sum(v)
        result.append(p)
    return result


def evaluate(rows,start,end):
    for r in rows:
        validate_features(r['features'])
        if r['outcome'] not in {'WIN','LOSS'} or r['label']!=int(r['outcome']=='WIN'):
            raise ValueError('Label policy violation')
        if stamp(r['feature_available_at'])>stamp(r['signal_at']) or stamp(r['resolved_at'])<stamp(r['signal_at']):
            raise ValueError('Temporal violation')
    boundaries=folds(rows,start,end); reports=[]; artifacts=[]; pooled={}
    for fold in boundaries:
        train_rows=fold['train']; test_rows=fold['test']
        counts=Counter(r['label'] for r in train_rows); test_counts=Counter(r['label'] for r in test_rows)
        report={k:v for k,v in fold.items() if k not in {'train','test'}}
        report.update(train_count=len(train_rows),test_count=len(test_rows),train_class_counts={str(k):v for k,v in counts.items()},
            test_class_counts={str(k):v for k,v in test_counts.items()},train_ids_hash=digest([r['id'] for r in train_rows]),
            test_ids_hash=digest([r['id'] for r in test_rows]),models={})
        support=POLICY['support']
        supported=(len(train_rows)>=support['train_total'] and min(counts.get(k,0) for k in (0,1))>=support['train_per_class']
                   and len(test_rows)>=support['test_total'] and min(test_counts.get(k,0) for k in (0,1))>=support['test_per_class'])
        report['status']='SUPPORTED_RESEARCH_METRICS' if supported else 'INSUFFICIENT_DATA'
        if supported:
            for kind,identity in [('prior',False),('logistic',False),('logistic',True),('shallow_tree',False),('shallow_tree',True)]:
                key=kind+('_with_strategy_id' if identity else '_without_strategy_id')
                p,artifact=train(train_rows,test_rows,kind,strategy_id=identity)
                aid=digest(artifact); artifacts.append(dict(artifact_id=aid,fold=fold['fold'],model=key,payload=artifact))
                slices={}
                for field in ('instrument','timeframe','family','strategy_id'):
                    groups=sorted({r['features'][field] for r in test_rows})
                    slices[field]={g:metrics([r['label'] for r in test_rows if r['features'][field]==g],
                        [v for r,v in zip(test_rows,p) if r['features'][field]==g]) for g in groups}
                report['models'][key]=dict(artifact_id=aid,metrics=metrics([r['label'] for r in test_rows],p),
                    operating_points=[filter_stats(test_rows,p,t) for t in POLICY['thresholds']],slices=slices)
                pooled.setdefault(key,[]).extend([(r,v) for r,v in zip(test_rows,p)])
        reports.append(report)
    summary={}
    predictions=[]
    for key,pairs in pooled.items():
        rr=[r for r,p in pairs]; pp=[p for r,p in pairs]
        summary[key]=dict(metrics=metrics([r['label'] for r in rr],pp),
            operating_points=[filter_stats(rr,pp,t) for t in POLICY['thresholds']])
        predictions.extend(dict(id=r['id'],model=key,probability=p) for r,p in pairs)
    learned=[k for k in summary if not k.startswith('prior')]
    best=max(learned,key=lambda k:summary[k]['metrics']['roc_auc']) if learned else None
    diagnostics={}
    for key in learned:
        valid=[f for f in reports if key in f['models']]
        diagnostics[key]=dict(
            auc='PASS' if all(f['models'][key]['metrics']['roc_auc']>=.58 for f in valid) else 'FAIL',
            baseline_brier='PASS' if all(f['models'][key]['metrics']['brier']<f['models']['prior_without_strategy_id']['metrics']['brier'] for f in valid) else 'FAIL',
            independent_sample='NOT_PROVEN; short reused window and overlapping strategy events',
            coverage='NOT_PROVEN; counts/coverage are reported, no invented qualifying floor',
            calibration='NOT_PROVEN; inspect calibration bins and baseline-relative proper scores',
            trading_consistency='PASS' if all((f['models'][key]['operating_points'][0]['after']['expectancy'] is not None and
                f['models'][key]['operating_points'][0]['after']['expectancy']>
                f['models'][key]['operating_points'][0]['before']['expectancy']) for f in valid) else 'FAIL',
            final_status='PASS_THROUGH')
    return dict(policy=POLICY,policy_hash=POLICY_ID,schema_id=SCHEMA_ID,label_policy=LABEL_POLICY,
        folds=reports,summary=summary,predictions_hash=digest(predictions),
        qualification_diagnostics=diagnostics,descriptive_best_learner=best,
        selection='descriptive AUC comparison only; no final-test model/threshold activation',
        filter_status='PASS_THROUGH' if summary else 'INSUFFICIENT_DATA',
        result='ML_NO_MEASURABLE_VALUE' if summary else 'INSUFFICIENT_DATA',
        result_scope='No qualified incremental value established; descriptive scores do not qualify deployment',
        execution_eligible=False),artifacts,predictions
