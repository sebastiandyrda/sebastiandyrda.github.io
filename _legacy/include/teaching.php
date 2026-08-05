<?php 
	$sub=(!empty($_GET['sub']))?strtolower($_GET['sub']):null;
	if(!empty($sub)&&is_file(dirname(__FILE__).'/teaching/'.$sub.'.php')){
		include('teaching/'.$sub.'.php');
	}else{	
?>
<div class="tekst">
<h3 class="red">Courses</h3>
<p>

UNIVERSITY OF TORONTO</p>
	<b>Intermediate Macroeconomics</b> (Fall 2015, Spring 2016, Fall 2016, Spring 2017)<br/>
	<b>Quantitative Macroeconomics (Ph.D.)</b> (Spring 2016, Spring 2017)<br/>
</p>
UNIVERSITY OF MINNESOTA</p>
    ECON 1101: <b>Principles of Microeconomics</b> (Fall 2010, Spring 2011)<br/>
	ECON 4731: <b>Advanced Macroeconomic Policy</b> (Fall 2012)<br/>
	ECON 4731: <b>Advanced Macroeconomic Policy</b> (Honors Course) (<a href="/files/olbert_paper.pdf">Fall 2013</a>, <a href="/files/ferrari_paper.pdf">Spring 2014</a>)<br/>
	ECO 2104: <b>Quantitative Macroeconomics</b> <a href="/files/santacreu_profitshifting_r2.pdf">(Winter 2016)</a><br/>

</p>
</div>
<?php 
	}