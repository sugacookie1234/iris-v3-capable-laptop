"""Bounded owner-turn orchestration. Decisions never grant tool authority."""
from dataclasses import dataclass, field, replace
from uuid import uuid4
from enum import Enum
import re
import time
from iris.desktop.commands import normalize
from iris.generalist.visuals import compound, validate

class Intent(str,Enum):
    CONVERSATION='conversation'
    LOCAL='local_information'
    TOOL='existing_tool'
    SKILL='active_skill'
    VISUAL='visual_explanation'
    RESEARCH='research'
    CLARIFY='clarification'

@dataclass(frozen=True)
class Decision:
    intent: Intent
    reason: str
    def __post_init__(self):
        if not isinstance(self.intent,Intent) or self.reason not in {'compound','followup','clock','allowlisted','explicit_search','unresolved','ordinary'}:
            raise ValueError('Invalid orchestration decision.')

class State(str,Enum):
    ACTIVE='active'
    PAUSED='paused'
    CANCELLED='cancelled'
    COMPLETE='complete'
    EXPIRED='expired'

@dataclass
class CompoundSkill:
    principal: float=1000
    years: int=10
    contribution: float=0
    rate: float=5
    compared_rate: float | None=None
    state: State=State.ACTIVE

    def parameters(self):
        return {key:getattr(self,key) for key in ('principal','rate','years','contribution','compared_rate')}
    def change(self,changes):
        if self.state is not State.ACTIVE:raise ValueError('Resume the example first.')
        if type(changes) is not dict or not changes or not set(changes)<=set(self.parameters()):raise ValueError('Invalid visual changes.')
        candidate=replace(self,**changes)
        candidate.visual()
        for key,value in changes.items():setattr(self,key,value)
    def reset(self):
        self.change({'principal':1000,'rate':5,'years':10,'contribution':0,'compared_rate':None})
    def update(self,rate,*,compare=False):
        if self.state is not State.ACTIVE:raise ValueError('Resume the active example first.')
        self.change({'compared_rate':rate} if compare else {'rate':rate,'compared_rate':None})
    def resume(self):
        if self.state is not State.PAUSED:raise ValueError('No paused example to resume.')
        self.state=State.ACTIVE
    def pause(self):self.state=State.PAUSED
    def cancel(self):self.state=State.CANCELLED
    def complete(self):self.state=State.COMPLETE
    def expire(self):self.state=State.EXPIRED
    def visual(self):
        first=compound(self.principal,self.rate,self.years,self.contribution)
        if self.compared_rate is None:return validate(first)
        second=compound(self.principal,self.compared_rate,self.years,self.contribution)
        return validate({'version':1,'kind':'line','title':'Hypothetical compound-interest comparison',
            'labels':[f'{self.rate:g}% annual rate',f'{self.compared_rate:g}% annual rate'],
            'points':[[a[0],a[1],b[1]] for a,b in zip(first['points'],second['points'])],
            'summary':first['summary']})

@dataclass
class ActiveContext:
    topic: str='compound interest'
    workflow: str='compound_interest_v1'
    visual_reference: str=field(default_factory=lambda:uuid4().hex)
    revision: int=0
    expires: float=0
    turns: int=0
    skill: CompoundSkill=field(default_factory=CompoundSkill)

_SMALL=dict(zip('zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split(),range(21)))
_RATE=re.compile(r'(?<![\w.,-])(-?\d+(?:\.\d+)?|'+ '|'.join(_SMALL)+r')\s*(?:percent|per cent|%)(?!\w)')

def rates(text):
    if re.search(r'\b(?:and|or|between)\b',text):return []
    found=[]
    for match in _RATE.finditer(text):
        prefix=text[:match.start()].strip().split()
        if prefix and prefix[-1] in _SMALL:return []
        token=match[1];found.append(float(_SMALL[token]) if token in _SMALL else float(token))
    return found

class Orchestrator:
    """Session-only public example state; no private memory/tools/provider access."""
    def __init__(self,*,clock=time.monotonic,ttl=900,max_turns=20):
        self.clock=clock;self.ttl=ttl;self.max_turns=max_turns;self.context=None
    def clear(self):self.context=None
    def _expire(self):
        if self.context and (self.clock()>=self.context.expires or self.context.turns>=self.max_turns):
            self.context.skill.expire();self.clear()
    def classify(self,text):
        if not isinstance(text,str) or not 1<=len(text.strip())<=12000:raise ValueError('Invalid owner turn.')
        self._expire();query=normalize(text)
        if re.fullmatch(r'(?:explain|show(?: me)?|teach me(?: about)?|demonstrate) (?:how )?compound interest(?: works)?',query):
            return Decision(Intent.VISUAL,'compound')
        if query.startswith(('/search ', 'search the web for ')):return Decision(Intent.RESEARCH,'explicit_search')
        from iris.desktop.local_time import response
        if response(query,'UTC') is not None:return Decision(Intent.LOCAL,'clock')
        if re.fullmatch(r'open (?:calculator|notepad|chrome|obsidian|file explorer)',query):return Decision(Intent.TOOL,'allowlisted')
        if query in ('open it again','bring it back','open it in the workspace','open that in the workspace'):
            return Decision(Intent.SKILL if self.context else Intent.CLARIFY,'followup' if self.context else 'unresolved')
        reference=bool(re.search(r'\b(?:compare|difference|gap|original|initial|interest rate|principal|contribute|contribution|monthly|years|balance|graph|workspace|percent|resume|pause|cancel|finish)\b|%',query))
        if reference:return Decision(Intent.SKILL if self.context else Intent.CLARIFY,'followup' if self.context else 'unresolved')
        return Decision(Intent.CONVERSATION,'ordinary')
    @staticmethod
    def _reply(text,**details):
        return {'reply':text,'spoken_reply':text,'route':'LOCAL','public_context':True,'public_context_query':'Discuss the public compound-interest example.',**details}
    def handle(self,text):
        decision=self.classify(text);query=normalize(text)
        if any(token in query for token in ('"', '`')) or re.match(r"(?:do not|don't|never|say |quote )",query):
            self.clear();return None
        if decision.intent is Intent.VISUAL:
            self.context=ActiveContext(expires=self.clock()+self.ttl)
        elif decision.intent is Intent.SKILL:
            context=self.context;skill=context.skill;context.turns+=1
            if query in ('open it again','bring it back','open it in the workspace','open that in the workspace') or re.fullmatch(r'(?:show(?: me)?|open|bring)(?: (?:me|it|that|the))?(?: graph| back| again| in the workspace| workspace)(?: again| back)?',query):
                return self.presentation(window_action='open')
            if query in ('close the graph','close graph','close the workspace'):
                return self._reply('The graph window has been asked to close. The example remains available.',window_action='close')
            if re.fullmatch(r'(?:cancel|stop|finish|complete|pause|resume)(?: (?:this|the))?(?: example| explanation| skill)?',query):
                operation=query.split()[0]
                if operation=='pause':skill.pause();return self._reply('The example is paused.')
                if operation=='resume':
                    try:skill.resume()
                    except ValueError as error:return self._reply(str(error))
                else:
                    skill.complete() if operation in ('finish','complete') else skill.cancel()
                    self.clear();return self._reply('The example is closed. No financial action was taken.')
            elif re.search(r'\b(?:original|initial|starting)\b',query) and re.search(r'\b(?:back|restore|return|reset)\b',query):
                if skill.state is not State.ACTIVE:return self._reply('Resume the paused example first.')
                skill.reset()
            elif re.search(r'\b(?:why|explain)\b',query) and re.search(r'\b(?:difference|different|gap|more|growth|balance|increase)\b',query):
                if skill.compared_rate is None:return self.presentation(prefix='The balance reflects the current principal, contributions and rate; earlier interest also earns interest. ')
                visual=skill.visual();last=visual['points'][-1]
                if skill.rate == skill.compared_rate:return self._reply('The rates and assumptions are identical, so the balances are equal. This is a hypothetical example, before fees and taxes.',visual=visual)
                return self._reply(f'At {skill.rate:g}% the balance is {last[1]:,.2f} units; at {skill.compared_rate:g}% it is {last[2]:,.2f}. The difference is {abs(last[1]-last[2]):,.2f} units after {skill.years} years. Each month, the higher rate applies to an increasingly larger balance, including earlier interest. These are hypothetical constant rates, before fees and taxes.',visual=visual)
            elif re.search(r'\b(?:contribute|contribution|principal|years)\b',query):
                numbers=re.findall(r'(?<![\w.])-?\d+(?:\.\d+)?',query)
                if len(numbers)!=1:return self._reply('Give one numeric principal, duration or monthly contribution.')
                key='contribution' if re.search(r'contribut',query) else 'principal' if 'principal' in query else 'years'
                value=float(numbers[0])
                if key=='years' and value.is_integer():value=int(value)
                try:skill.change({key:value})
                except ValueError:return self._reply('That input is outside the supported educational limits. The example is unchanged.')
            elif re.search(r'\b(?:what if|rate|compare|use|change|increase|decrease|make)\b',query):
                values=rates(query)
                if len(values)!=1:return self._reply('Which single annual percentage rate should I use for this example?')
                try:skill.update(values[0],compare=bool(re.search(r'\bcompar',query)))
                except ValueError:return self._reply('Use one annual rate from zero to 100 percent, and resume the example if it is paused.')
            else:return self._reply('Do you want to change the annual rate, compare another rate, or restore the original example?')
        elif decision.intent is Intent.CLARIFY:
            # Only referential educational requests are intercepted; ordinary
            # finance questions still use the existing conversation dispatcher.
            if re.search(r'\b(?:that|example|rate were|original|resume)\b',query):
                return self._reply('There is no active example. Ask me to explain compound interest first.')
            self.clear();return None
        else:
            # Any unrelated owner turn releases this narrow skill context.
            self.clear();return None
        return self.presentation()

    def presentation(self,*,prefix='',window_action=None):
        skill=self.context.skill;visual=skill.visual();last=visual['points'][-1]
        text=f'Compound interest earns interest on earlier interest. Starting with {skill.principal:,.2f} units at {skill.rate:g}% annually, compounded monthly for {skill.years} years, with {skill.contribution:,.2f} units contributed at each month end, the balance is {last[1]:,.2f} units.'
        if skill.compared_rate is not None:text+=f' At {skill.compared_rate:g}% the balance is {last[2]:,.2f} units; the difference is {abs(last[1]-last[2]):,.2f} units.'
        text+=' No fees or taxes; hypothetical constant rates, not forecasts.'
        result=self._reply(prefix+text,visual=visual)
        result['spoken_reply']=f'At {skill.rate:g} percent, the final balance is {last[1]:,.2f} units.' + (f' At {skill.compared_rate:g} percent, it is {last[2]:,.2f} units.' if skill.compared_rate is not None else '')
        if window_action:result['window_action']=window_action
        return result
