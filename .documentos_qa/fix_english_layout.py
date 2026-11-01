from zipfile import ZipFile,ZIP_DEFLATED
from lxml import etree as E
p='entregas/TCC_Research_Proposal_Rodrigo_English.docx'; W='http://schemas.openxmlformats.org/wordprocessingml/2006/main'; ns={'w':W}
with ZipFile(p) as z: parts={n:z.read(n) for n in z.namelist()}
r=E.fromstring(parts['word/document.xml']);ps=r.find('w:body',ns).findall('w:p',ns)
for i,after in [(4,1200),(5,0),(6,400),(7,800)]:
 pr=ps[i].find('w:pPr',ns);sp=pr.find('w:spacing',ns);sp.set('{'+W+'}after',str(after))
for i in [27,31,34,45,47,50,53,56,58,60,62,64,66,68,70,72,74,78,86]:
 pr=ps[i].find('w:pPr',ns);k=E.SubElement(pr,'{'+W+'}keepNext');k.set('{'+W+'}val','1')
parts['word/document.xml']=E.tostring(r,xml_declaration=True,encoding='UTF-8',standalone=True)
with ZipFile(p,'w',ZIP_DEFLATED) as z:
 for n,b in parts.items():z.writestr(n,b)
